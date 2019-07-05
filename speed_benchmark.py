import argparse
from itertools import cycle
from multiprocessing import cpu_count
import os
import platform
import re
import requests
from statistics import mean
import subprocess
import sys
from threading import Thread, Lock
from time import time, sleep
if platform.system().lower().find('windows') == 0:
    from win32com.client import GetObject
from prettytable import PrettyTable
import psutil
from alprstream import AlprStream
from openalpr import Alpr
from vehicleclassifier import VehicleClassifier


PYTHON_VERSION = platform.python_version_tuple()[0]
if PYTHON_VERSION == '3':
    from urllib.request import urlretrieve
elif PYTHON_VERSION == '2':
    from urllib import urlretrieve
else:
    raise OSError('Expected Python version 2 or 3, but received {}'.format(PYTHON_VERSION))


def get_cpu_model(operating):
    if operating == 'linux':
        cpu_info = subprocess.check_output('lscpu').strip().decode().split('\n')
        model_regex = re.compile('^Model name')
        model = [c for c in cpu_info if model_regex.match(c)]
        model = model[0].split(':')[-1].strip()
    elif operating == 'windows':
        root_winmgmts = GetObject('winmgmts:root\cimv2')
        cpus = root_winmgmts.ExecQuery('Select * from Win32_Processor')
        model = cpus[0].Name
    else:
        raise ValueError('Expected OS to be linux or windows, but received {}'.format(operating))
    model = re.sub('\([RTM]+\)', '', model)
    return model


def get_instance_type():
    """Attempt to query AWS metadata endpoint for instance type.

    :return str instance_type: AWS designation (or dash for NA).
    """
    try:
        r = requests.get('http://169.254.169.254/latest/meta-data/instance-type')
        r.raise_for_status()
        instance_type = r.text
    except requests.exceptions.ConnectionError:
        instance_type = '-'
    return instance_type


def ptable_to_csv(table, filename, mode, headers=True):
    """Save PrettyTable results to a CSV file.

    Adapted from @AdamSmith https://stackoverflow.com/questions/32128226

    :param PrettyTable table: Table object to get data from.
    :param str filename: Filepath for the output CSV.
    :param str mode: File writing mode for ``open()`` function.
    :param bool headers: Whether to include the header row in the CSV.
    :return: None
    """
    raw = table.get_string()
    data = [tuple(filter(None, map(str.strip, splitline)))
            for line in raw.splitlines()
            for splitline in [str(line).split('|')] if len(splitline) > 1]
    if table.title is not None:
        data = data[1:]
    if not headers:
        data = data[1:]
    with open(filename, mode) as f:
        for d in data:
            f.write('{}\n'.format(','.join(d)))


class AlprBench:
    """Benchmark OpenALPR software speed for various video resolutions.

    :param int num_streams: Starting number of camera streams to simulate.
    :param int step: Number of streams to add each time ``thres`` CPU
        utilization is not achieved.
    :param str or [str] resolution: Resolution(s) of videos to benchmark.
    :param int or float: Target for lowest average CPU utilization. If
        ``thres > 0``, experiments will be run with additional streams until
        the threshold condition is met (recommended value 95).
    :param bool gpu: Whether or not to use GPU acceleration.
    :param int batch_size: Number of images to process simultaneously on GPU.
    :param str runtime: Path to runtime data folder.
    :param str config: Path to OpenALPR configuration file.
    :param bool quiet: Suppress all output besides final results.
    """
    def __init__(self, num_streams, step, resolution, thres, gpu=False,
                 batch_size=10, runtime=None, config=None, quiet=False):

        # Transfer parameters to attributes
        self.quiet = quiet
        self.message('Initializing...')
        self.num_streams = num_streams
        self.step = step
        if isinstance(resolution, str):
            if resolution == 'all':
                self.resolution = ['vga', '720p', '1080p', '4k']
            else:
                self.resolution = [resolution]
        elif isinstance(resolution, list):
            self.resolution = resolution
        else:
            raise ValueError('Expected list or str for resolution, but received {}'.format(resolution))
        self.thres = thres
        self.gpu = gpu
        self.batch_size = batch_size

        # Detect operating system and alpr version
        if platform.system().lower().find('linux') == 0:
            self.operating = 'linux'
            self.cpu_model = get_cpu_model('linux')
        elif platform.system().lower().find('windows') == 0:
            self.operating = 'windows'
            self.cpu_model = get_cpu_model('windows')
        else:
            raise OSError('Detected OS other than Linux or Windows')
        self.message('\tOperating system: {}'.format(self.operating.capitalize()))
        self.message('\tCPU model: {}'.format(self.cpu_model))
        alpr = Alpr('us', '', '')
        self.message('\tOpenALPR version: {}'.format(alpr.get_version()))
        alpr.unload()

        # Prepare other attributes
        if self.operating == 'linux':
            self.downloads = '/tmp/alprbench'
        else:
            self.downloads = os.path.join(os.environ['TEMP'], 'alprbench')
        if not os.path.exists(self.downloads):
            os.mkdir(self.downloads)
        self.cpu_usage = {r: [] for r in self.resolution}
        self.threads_active = False
        self.frame_counter = 0
        self.mutex = Lock()
        self.streams = []
        self.round_robin = cycle(range(self.num_streams))
        self.results = PrettyTable()
        self.results.field_names = ['Resolution', 'Total FPS', 'CPU (Avg)', 'CPU (Max)', 'Frames']

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
        self.message('\tRuntime data: {}'.format(self.runtime))
        self.message('\tOpenALPR configuration: {}'.format(self.config))

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
            self.message('\tLowest average CPU usage {:.1f}%'.format(min_cpu))
            current_streams += self.step
        final_streams = current_streams - self.step
        self.results.title = 'OpenALPR Speed: {} stream(s) on {} threads'.format(
            final_streams, cpu_count())
        print(self.results)
        return final_streams

    def download_benchmarks(self):
        """Save requested benchmark videos locally.

        :return [str] videos: Filepaths to downloaded videos.
        """
        videos = []
        endpoint = 'https://github.com/openalpr/speed_benchmark/releases/download/v1'
        files = ['vga.mp4', '720p.mp4', '1080p.mp4', '4k.mp4']
        existing = os.listdir(self.downloads)
        self.message('Downloading benchmark videos...')
        for f in files:
            res = f.split('.')[0]
            if res in self.resolution:
                out = os.path.join(self.downloads, f)
                videos.append(out)
                if f not in existing:
                    _ = urlretrieve('{}/{}'.format(endpoint, f), out)
                    self.message('\tDownloaded {}'.format(res))
                else:
                    self.message('\tFound local {}'.format(res))
        return videos

    def format_results(self, num_streams, resolution, elapsed):
        """Update results table.

        :param int num_streams: Number of streams used in the experiment.
        :param str resolution: Resolution of the video that was benchmarked.
        :param float elapsed: Time to process video (in seconds).
        :return: None
        """
        total_fps = '{:.1f}'.format(self.frame_counter / elapsed)
        avg_cpu = '{:.1f}'.format(mean(self.cpu_usage[resolution]))
        max_cpu = '{:.1f}'.format(max(self.cpu_usage[resolution]))
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

        # Compile regex
        if self.operating == 'linux':
            name_regex = re.compile('(?<=\/)[^\.\/]+')
        elif self.operating == 'windows':
            name_regex = re.compile('(?<=\\\)[^\.\\\]+')
        self.threads_active = True

        # Run experiment
        self.message('Testing with {} stream(s)...'.format(num_streams))
        for v in videos:
            res = name_regex.findall(v)[-1]
            self.message('\tProcessing {}'.format(res))
            self.frame_counter = 0
            threads = []
            for s in self.streams:
                s.connect_video_file(v, 0)

            start = time()
            if self.gpu:
                self.worker(res)
            else:
                for i in range(cpu_count()):
                    threads.append(Thread(target=self.worker, args=(res, )))
                    threads[i].setDaemon(True)
                    threads[i].start()
                while len(threads) > 0:
                    try:
                        threads = [t.join() for t in threads if t is not None and t.isAlive()]
                    except KeyboardInterrupt:
                        print('\n\nCtrl-C received! Sending kill to threads...')
                        self.threads_active = False
                        break
            elapsed = time() - start
            self.format_results(num_streams, res, elapsed)
        min_cpu = min(mean(self.cpu_usage[r]) for r in self.cpu_usage.keys())
        return min_cpu

    def worker(self, resolution):
        """Thread for a single Alpr and VehicleClassifier instance."""
        if self.gpu:
            try:
                alpr = Alpr('us', self.config, self.runtime, use_gpu=True, gpu_batch_size=self.batch_size)
            except TypeError:
                print('Your Alpr binding version does not support GPU')
                sys.exit(1)
        else:
            alpr = Alpr('us', self.config, self.runtime)
        vehicle = VehicleClassifier(self.config, self.runtime)
        active_streams = sum([s.video_file_active() for s in self.streams])
        total_queue = sum([s.get_queue_size() for s in self.streams])
        while active_streams or total_queue > 0:
            if not self.threads_active:
                break
            active_streams = sum([s.video_file_active() for s in self.streams])
            total_queue = sum([s.get_queue_size() for s in self.streams])
            idx = next(self.round_robin)
            if self.streams[idx].get_queue_size() == 0:
                sleep(0.1)
                continue
            if self.gpu:
                batch_results = self.streams[idx].process_batch(alpr)
                results = batch_results[0]
            else:
                results = self.streams[idx].process_frame(alpr)
            if results['epoch_time'] > 0 and results['processing_time_ms'] > 0:
                _ = self.streams[idx].pop_completed_groups_and_recognize_vehicle(vehicle)
                self.mutex.acquire()
                if self.gpu:
                    self.frame_counter += len(batch_results)
                else:
                    self.frame_counter += 1
                if self.frame_counter % 10 == 0:
                    self.cpu_usage[resolution].append(psutil.cpu_percent())
                self.mutex.release()


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Benchmark OpenALPR software speed at various video resolutions. Prints an ASCII table of results '
                    'to stdout and optionally saves to CSV (if specified). If the output file already exists, results '
                    'will be appended to existing data.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('output', nargs='?', type=str, default=None, help='filepath to save CSV of results')
    parser.add_argument('-b', '--batch_size', type=int, default=10, help='for GPU usage only')
    parser.add_argument('-g', '--gpu', action='store_true', help='run on GPU if available')
    parser.add_argument('-q', '--quiet', action='store_true', help='suppress all output besides final results')
    parser.add_argument('-r', '--resolution', type=str, default='all', help='video resolution to benchmark on')
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
        args.batch_size,
        args.runtime,
        args.config,
        args.quiet)
    num_streams = bench()

    if args.output is not None:
        # Add CPU model and stream count to results table
        table = bench.results
        n_rows = len(table._rows)
        table.add_column('CPU Model', [bench.cpu_model] * n_rows)
        table.add_column('AWS Instance', [get_instance_type()] * n_rows)
        table.add_column('Streams', [num_streams] * n_rows)

        # Save results to disk
        save = os.path.realpath(args.output)
        print('Saving results to {}'.format(save))
        if os.path.exists(save):
            ptable_to_csv(table, save, 'a', headers=False)
        else:
            ptable_to_csv(table, save, 'w')
