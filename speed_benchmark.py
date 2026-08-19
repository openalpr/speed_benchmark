import argparse
import csv
from itertools import cycle
from multiprocessing import cpu_count
import os
import platform
import re
import requests
from statistics import mean
import subprocess
import sys
import tempfile
from threading import Thread, Lock
from time import time, sleep
if platform.system() == 'Windows':
    from win32com.client import GetObject
from prettytable import PrettyTable
import psutil
from alprstream import AlprStream
from openalpr import Alpr
from openalpr import VehicleClassifier

RESOLUTIONS = ['vga', '720p', '1080p', '4k']
METADATA_ENDPOINT = 'http://169.254.169.254/latest'


def get_cpu_model(operating):
    if operating == 'linux':
        env = dict(os.environ, LC_ALL='C')  # lscpu localizes 'Model name' otherwise
        cpu_info = subprocess.check_output('lscpu', env=env).strip().decode().split('\n')
        model_regex = re.compile(r'^Model name')
        model = [c for c in cpu_info if model_regex.match(c)]
        model = model[0].split(':')[-1].strip()
    elif operating == 'windows':
        root_winmgmts = GetObject(r'winmgmts:root\cimv2')
        cpus = root_winmgmts.ExecQuery('Select * from Win32_Processor')
        model = cpus[0].Name
    else:
        raise ValueError(f'Expected OS to be linux or windows, but received {operating}')
    model = re.sub(r'\([RTM]+\)', '', model)
    return model


def get_instance_type():
    """Attempt to query AWS metadata endpoint for instance type.

    Supports IMDSv2 (token-based) with fallback to IMDSv1 if the token
    request is rejected.

    :return str instance_type: AWS designation (or dash for NA).
    """
    try:
        headers = {}
        token = requests.put(
            f'{METADATA_ENDPOINT}/api/token',
            headers={'X-aws-ec2-metadata-token-ttl-seconds': '60'},
            timeout=2)
        if token.ok:
            headers['X-aws-ec2-metadata-token'] = token.text
        r = requests.get(f'{METADATA_ENDPOINT}/meta-data/instance-type', headers=headers, timeout=2)
        r.raise_for_status()
        instance_type = r.text
    except requests.exceptions.RequestException:
        instance_type = '-'
    return instance_type


def download_file(url, out):
    """Download a file to disk, atomically renaming on completion so an
    interrupted download never leaves a truncated file at ``out``.

    :param str url: Source URL.
    :param str out: Destination filepath.
    :return: None
    """
    partial = f'{out}.part'
    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(partial, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    os.replace(partial, out)


def ptable_to_csv(table, filename, mode, headers=True):
    """Save PrettyTable results to a CSV file.

    :param PrettyTable table: Table object to get data from.
    :param str filename: Filepath for the output CSV.
    :param str mode: File writing mode for ``open()`` function.
    :param bool headers: Whether to include the header row in the CSV.
    :return: None
    """
    with open(filename, mode, newline='') as f:
        writer = csv.writer(f)
        if headers:
            writer.writerow(table.field_names)
        writer.writerows(table.rows)


class AlprBench:
    """Benchmark OpenALPR software speed for various video resolutions.

    :param int num_streams: Starting number of camera streams to simulate.
    :param int step: Number of streams to add each time ``thres`` CPU
        utilization is not achieved.
    :param str or [str] resolution: Resolution(s) of videos to benchmark.
    :param int or float thres: Target for lowest average CPU utilization. If
        ``thres > 0``, experiments will be run with additional streams until
        the threshold condition is met (recommended value 95).
    :param bool gpu: Whether or not to use GPU acceleration.
    :param str runtime: Path to runtime data folder.
    :param str config: Path to OpenALPR configuration file.
    :param bool quiet: Suppress all output besides final results.
    """
    def __init__(self, num_streams, step, resolution, thres, gpu=False, runtime=None, config=None, quiet=False):

        # Transfer parameters to attributes
        self.quiet = quiet
        self.message('Initializing...')
        self.num_streams = num_streams
        self.step = step
        if isinstance(resolution, str):
            resolution = [resolution]
        elif not isinstance(resolution, list):
            raise ValueError(f'Expected list or str for resolution, but received {resolution}')
        resolution = [r.strip().lower() for r in resolution]
        if 'all' in resolution:
            resolution = list(RESOLUTIONS)
        invalid = [r for r in resolution if r not in RESOLUTIONS]
        if invalid:
            raise ValueError('Invalid resolution(s) {}: choose from {}'.format(
                ', '.join(invalid), ', '.join(RESOLUTIONS + ['all'])))
        self.resolution = list(dict.fromkeys(resolution))  # dedupe, preserve order
        if not 0 <= thres < 100:
            raise ValueError(f'thres must be in [0, 100), but received {thres} '
                             '(a threshold of 100+ can never be met and would add streams forever)')
        self.thres = thres
        self.gpu = gpu

        # Detect operating system and alpr version
        if platform.system() == 'Linux':
            self.operating = 'linux'
        elif platform.system() == 'Windows':
            self.operating = 'windows'
        else:
            raise OSError('Detected OS other than Linux or Windows')
        self.cpu_model = get_cpu_model(self.operating)
        self.message(f'\tOperating system: {self.operating.capitalize()}')
        self.message(f'\tCPU model: {self.cpu_model}')

        # Define default runtime and config paths if not specified
        if runtime is not None:
            self.runtime = runtime
        else:
            self.runtime = '/usr/share/openalpr/runtime_data'
            if self.operating == 'windows':
                self.runtime = 'C:/OpenALPR/Agent' + self.runtime
        if config is not None:
            self.config = config
        else:
            self.config = '/usr/share/openalpr/config/openalpr.defaults.conf'
            if self.operating == 'windows':
                self.config = 'C:/OpenALPR/Agent' + self.config
        self.message(f'\tRuntime data: {self.runtime}')
        self.message(f'\tOpenALPR configuration: {self.config}')
        alpr = Alpr('us', self.config, self.runtime)
        self.message(f'\tOpenALPR version: {alpr.get_version()}')
        alpr.unload()

        # Prepare other attributes
        self.downloads = os.path.join(tempfile.gettempdir(), 'alprbench')
        os.makedirs(self.downloads, exist_ok=True)
        self.cpu_usage = {r: [] for r in self.resolution}
        self.threads_active = False
        self.frame_counter = 0
        self.mutex = Lock()
        self.streams = []
        self.round_robin = cycle(range(self.num_streams))
        self.results = PrettyTable()
        self.results.field_names = ['Resolution', 'Total FPS', 'CPU (Avg)', 'CPU (Max)', 'Frames']

        # Enable GPU acceleration
        if self.gpu:
            with open(self.config, 'r') as f:
                lines = [l.strip() for l in f.read().split('\n') if l != '']
            lines = [l for l in lines if not l.startswith('hardware_acceleration')]
            lines.append('hardware_acceleration = 1')
            self.config = os.path.join(self.downloads, 'openalpr.conf')
            with open(self.config, 'w') as f:
                for l in lines:
                    f.write(f'{l}\n')

    def __call__(self):
        """Run threaded benchmarks on all requested resolutions.

        :return int final_streams: Number of streams used to achieve the
            threshold CPU utilization.
        """
        videos = self.download_benchmarks()
        current_streams = self.num_streams
        min_cpu = 0
        while min_cpu <= self.thres:
            min_cpu = self.run_experiment(current_streams, videos)
            self.message(f'\tLowest average CPU usage {min_cpu:.1f}%')
            current_streams += self.step
        final_streams = current_streams - self.step
        self.results.title = f'OpenALPR Speed: {final_streams} stream(s) on {cpu_count()} threads'
        print(self.results)
        return final_streams

    def download_benchmarks(self):
        """Save requested benchmark videos locally.

        :return [str] videos: Filepaths to downloaded videos.
        """
        videos = []
        endpoint = 'https://github.com/openalpr/speed_benchmark/releases/download/v1'
        self.message('Downloading benchmark videos...')
        for res in self.resolution:
            filename = f'{res}.mp4'
            out = os.path.join(self.downloads, filename)
            videos.append(out)
            if not os.path.exists(out):
                download_file(f'{endpoint}/{filename}', out)
                self.message(f'\tDownloaded {res}')
            else:
                self.message(f'\tFound local {res}')
        return videos

    def format_results(self, num_streams, resolution, elapsed):
        """Update results table.

        :param int num_streams: Number of streams used in the experiment.
        :param str resolution: Resolution of the video that was benchmarked.
        :param float elapsed: Time to process video (in seconds).
        :return: None
        """
        samples = self.cpu_usage[resolution]
        total_fps = f'{self.frame_counter / elapsed:.1f}'
        avg_cpu = f'{mean(samples):.1f}' if samples else '-'
        max_cpu = f'{max(samples):.1f}' if samples else '-'
        avg_frames = int(self.frame_counter / num_streams)
        self.results.add_row([resolution, total_fps, avg_cpu, max_cpu, avg_frames])

    def message(self, msg):
        """Control verbosity of output.

        :param str msg: Message to display.
        :return: None
        """
        if not self.quiet:
            print(msg)

    def run_experiment(self, num_streams, videos):

        # Reset streams, CPU stats, and table from previous experiments
        self.streams = [AlprStream(10, False) for _ in range(num_streams)]
        self.round_robin = cycle(range(num_streams))
        self.cpu_usage = {r: [] for r in self.resolution}
        self.results.clear_rows()
        self.threads_active = True

        # Run experiment
        self.message(f'Testing with {num_streams} stream(s)...')
        for v in videos:
            res = os.path.splitext(os.path.basename(v))[0]
            self.message(f'\tProcessing {res}')
            self.frame_counter = 0
            for s in self.streams:
                s.connect_video_file(v, 0)
            threads = [Thread(target=self.worker, args=(res, ), daemon=True)
                       for _ in range(cpu_count())]
            psutil.cpu_percent()  # reset baseline so the first worker sample is not a meaningless 0.0
            start = time()
            for t in threads:
                t.start()
            try:
                for t in threads:
                    while t.is_alive():
                        t.join(timeout=0.5)
            except KeyboardInterrupt:
                print('\n\nCtrl-C received! Sending kill to threads...')
                self.threads_active = False
                for t in threads:
                    t.join()
                sys.exit(130)
            elapsed = time() - start
            self.format_results(num_streams, res, elapsed)
        sampled = [samples for samples in self.cpu_usage.values() if samples]
        if not sampled:
            self.message('\tNo CPU samples collected, stopping search')
            return float('inf')
        min_cpu = min(mean(samples) for samples in sampled)
        return min_cpu

    def worker(self, resolution):
        """Thread for a single Alpr and VehicleClassifier instance."""
        alpr = Alpr('us', self.config, self.runtime)
        vehicle = VehicleClassifier(self.config, self.runtime)
        try:
            while self.threads_active:
                active_streams = sum(s.video_file_active() for s in self.streams)
                total_queue = sum(s.get_queue_size() for s in self.streams)
                if not active_streams and total_queue == 0:
                    break
                with self.mutex:
                    idx = next(self.round_robin)
                if self.streams[idx].get_queue_size() == 0:
                    sleep(0.1)
                    continue
                results = self.streams[idx].process_frame(alpr)
                if results['epoch_time'] > 0 and results['processing_time_ms'] > 0:
                    _ = self.streams[idx].pop_completed_groups_and_recognize_vehicle(vehicle)
                    with self.mutex:
                        self.frame_counter += 1
                        if self.frame_counter % 10 == 0:
                            self.cpu_usage[resolution].append(psutil.cpu_percent())
        finally:
            alpr.unload()
            if hasattr(vehicle, 'unload'):
                vehicle.unload()


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Benchmark OpenALPR software speed at various video resolutions. Prints an ASCII table of results '
                    'to stdout and optionally saves to CSV (if specified). If the output file already exists, results '
                    'will be appended to existing data.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('output', nargs='?', type=str, default=None, help='filepath to save CSV of results')
    parser.add_argument('-g', '--gpu', action='store_true', help='run on GPU if available')
    parser.add_argument('-q', '--quiet', action='store_true', help='suppress all output besides final results')
    parser.add_argument('-r', '--resolution', type=str, default='all',
                        help='video resolution(s) to benchmark on, comma separated: {} or all'.format(
                            ', '.join(RESOLUTIONS)))
    parser.add_argument('-s', '--streams', type=int, default=1, help='starting number of camera streams to simulate')
    parser.add_argument('-t', '--thres', type=int, default=0, help='target for lowest average CPU utilization')
    parser.add_argument('--step', type=int, default=1, help='number of streams to add each time thres is not achieved')
    parser.add_argument('--config', type=str, help='path to OpenALPR config, detects Windows/Linux and uses defaults')
    parser.add_argument('--runtime', type=str, help='path to runtime data, detects Windows/Linux and uses defaults')
    args = parser.parse_args()

    # Run benchmarks
    if ',' in args.resolution:
        args.resolution = [r.strip() for r in args.resolution.split(',')]
    bench = AlprBench(
        args.streams,
        args.step,
        args.resolution,
        args.thres,
        args.gpu,
        args.runtime,
        args.config,
        args.quiet)
    num_streams = bench()

    if args.output is not None:
        # Add CPU model and stream count to results table
        table = bench.results
        n_rows = len(table.rows)
        table.add_column('CPU Model', [bench.cpu_model] * n_rows)
        table.add_column('AWS Instance', [get_instance_type()] * n_rows)
        table.add_column('Streams', [num_streams] * n_rows)

        # Save results to disk
        save = os.path.realpath(args.output)
        print(f'Saving results to {save}')
        if os.path.exists(save):
            ptable_to_csv(table, save, 'a', headers=False)
        else:
            ptable_to_csv(table, save, 'w')
