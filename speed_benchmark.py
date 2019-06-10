import argparse
from itertools import cycle
from multiprocessing import cpu_count
import os
import platform
import re
from statistics import mean
import subprocess
from threading import Thread, Lock
from time import time, sleep
import urllib
from prettytable import PrettyTable
import psutil
from alprstream import AlprStream
from openalpr import Alpr
from vehicleclassifier import VehicleClassifier


def get_cpu_model(operating):
    if operating == 'linux':
        cpu_info = subprocess.check_output('lscpu').strip().decode().split('\n')
        model_regex = re.compile('^Model name')
        model = [c for c in cpu_info if model_regex.match(c)]
        model = model[0].split(':')[-1].strip()
    elif operating == 'windows':
        model = platform.processor()
    else:
        raise ValueError('Expected OS to be linux or windows, but received {}'.format(operating))
    return model


class AlprBench:
    """Benchmark OpenALPR software speed for various video resolutions.

    :param int num_streams: Number of camera streams to simulate.
    :param str or [str] resolution: Resolution(s) of videos to benchmark.
    :param str downloads: Folder to save benchmark videos to.
    :param str runtime: Path to runtime data folder.
    :param str config: Path to OpenALPR configuration file.
    :param bool quiet: Suppress all output besides final results.
    """
    def __init__(self, num_streams, resolution, downloads='/tmp/alprbench', runtime=None, config=None, quiet=False):

        # Transfer parameters to attributes
        self.quiet = quiet
        self.message('Initializing...')
        self.num_streams = num_streams
        if isinstance(resolution, str):
            if resolution == 'all':
                self.resolution = ['vga', '720p', '1080p', '4k']
            else:
                self.resolution = [resolution]
        elif isinstance(resolution, list):
            self.resolution = resolution
        else:
            raise ValueError('Expected list or str for resolution, but received {}'.format(resolution))
        self.downloads = downloads
        if not os.path.exists(self.downloads):
            os.mkdir(self.downloads)

        # Prepare other attributes
        self.cpu_usage = {r: [] for r in self.resolution}
        self.threads_active = False
        self.frame_counter = 0
        self.mutex = Lock()
        self.streams = []
        self.round_robin = cycle(range(self.num_streams))
        self.results = PrettyTable()
        self.results.field_names = ['Resolution', 'Total FPS', 'CPU (Avg)', 'CPU (Max)', 'Frames']
        self.results.title = 'OpenALPR Speed: {} stream(s) on {} threads'.format(
            self.num_streams, cpu_count())

        # Detect operating system
        if platform.system().lower().find('linux') == 0:
            operating = 'linux'
            self.message('\tOperating system: Linux')
            self.message('\tCPU model: {}'.format(get_cpu_model('linux')))
        elif platform.system().lower().find('windows') == 0:
            operating = 'windows'
            self.message('\tOperating system: Windows')
            self.message('\tCPU model: {}'.format(get_cpu_model('windows')))
        else:
            raise OSError('Detected OS other than Linux or Windows')

        # Define default runtime and config paths if not specified
        if runtime is None:
            self.runtime = '/usr/share/openalpr/runtime_data'
            if operating == 'windows':
                self.runtime = 'C:/OpenALPR/Agent' + self.runtime
        if config is None:
            self.config = '/usr/share/openalpr/config/openalpr.defaults.conf'
            if operating == 'windows':
                self.config = 'C:/OpenALPR/Agent' + self.config
        self.message('\tRuntime data: {}'.format(self.runtime))
        self.message('\tOpenALPR configuration: {}'.format(self.config))

    def __call__(self):
        """Run threaded benchmarks on all requested resolutions."""
        videos = self.download_benchmarks()
        self.streams = [AlprStream(10, False) for _ in range(self.num_streams)]
        name_regex = re.compile('(?<=\/)[^\.\/]+')
        self.threads_active = True

        for v in videos:
            res = name_regex.findall(v)[-1]
            self.message('Processing {}...'.format(res))
            self.frame_counter = 0
            threads = []
            for s in self.streams:
                s.connect_video_file(v, 0)
            for i in range(cpu_count()):
                threads.append(Thread(target=self.worker, args=(res, )))
                threads[i].setDaemon(True)
            start = time()
            for t in threads:
                t.start()
            while len(threads) > 0:
                try:
                    threads = [t.join() for t in threads if t is not None and t.isAlive()]
                except KeyboardInterrupt:
                    print('\n\nCtrl-C received! Sending kill to threads...')
                    self.threads_active = False
                    break
            elapsed = time() - start
            self.format_results(res, elapsed)
        print(self.results)

    def download_benchmarks(self):
        """Save requested benchmark videos locally.

        :return [str] videos: Filepaths to downloaded videos.
        """
        videos = []
        endpoint = 'http://download.openalpr.com/bench'
        files = ['vga.webm', '720p.mp4', '1080p.mp4', '4k.mp4']
        existing = os.listdir(self.downloads)
        self.message('Downloading benchmark videos...')
        for f in files:
            res = f.split('.')[0]
            if res in self.resolution:
                out = os.path.join(self.downloads, f)
                videos.append(out)
                if f not in existing:
                    _ = urllib.urlretrieve(os.path.join(endpoint, f), out)
                    self.message('\tDownloaded {}'.format(res))
                else:
                    self.message('\tFound local {}'.format(res))
        return videos

    def format_results(self, resolution, elapsed):
        """Update results table.

        :param str resolution: Resolution of the video that was benchmarked.
        :param float elapsed: Time to process video (in seconds).
        :return: None
        """
        total_fps = '{:.1f}'.format(self.frame_counter / elapsed)
        avg_cpu = '{:.1f}'.format(mean(self.cpu_usage[resolution]))
        max_cpu = '{:.1f}'.format(max(self.cpu_usage[resolution]))
        avg_frames = int(self.frame_counter / self.num_streams)
        self.results.add_row([resolution, total_fps, avg_cpu, max_cpu, avg_frames])

    def message(self, msg):
        """Control verbosity of output.

        :param str msg: Message to display.
        :return: None
        """
        if not self.quiet:
            print(msg)

    def worker(self, resolution):
        """Thread for a single Alpr and VehicleClassifier instance."""
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
            results = self.streams[idx].process_frame(alpr)
            if results['epoch_time'] > 0 and results['processing_time_ms'] > 0:
                _ = self.streams[idx].pop_completed_groups_and_recognize_vehicle(vehicle)
                self.mutex.acquire()
                self.frame_counter += 1
                if self.frame_counter % 10 == 0:
                    self.cpu_usage[resolution].append(psutil.cpu_percent())
                self.mutex.release()


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Benchmark OpenALPR software speed at various video resolutions',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-d', '--download_dir', type=str, default='/tmp/alprbench', help='folder to save videos')
    parser.add_argument('-q', '--quiet', action='store_true', help='suppress all output besides final results')
    parser.add_argument('-r', '--resolution', type=str, default='all', help='video resolution to benchmark on')
    parser.add_argument('-s', '--streams', type=int, default=1, help='number of camera streams to simulate')
    parser.add_argument('--config', type=str, help='path to OpenALPR config, detects Windows/Linux and uses defaults')
    parser.add_argument('--runtime', type=str, help='path to runtime data, detects Windows/Linux and uses defaults')
    args = parser.parse_args()

    if ',' in args.resolution:
        args.resolution = [r.strip() for r in args.resolution.split(',')]
    bench = AlprBench(
        args.streams,
        args.resolution,
        args.download_dir,
        args.runtime,
        args.config,
        args.quiet)
    bench()
