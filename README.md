# speed_benchmark 

Drive OpenALPR on all CPU cores to benchmark speed for various video resolutions

## Prequisites

* OpenALPR commercial license (2-week evaluation licenses can be obtained from 
[here](https://license.openalpr.com/evalrequest/))
* Ubuntu 18.04, Ubuntu 16.04, or Windows 10
* Python (2 or 3)

## Installation

Generic

1. Download the OpenALPR [SDK](http://doc.openalpr.com/sdk.html#installation) 
2. Clone this repository `git clone https://github.com/addisonklinke/openalpr-consulting.git`
3. Install the Python requirements `pip install -r requirements.txt`

Docker

```bash
docker run -it --rm -v /etc/openalpr:/etc/openalpr/ openalpr/commercial-agent /bin/bash
apt update && apt install -y curl python-pip git
git clone https://github.com/openalpr/speed_benchmark.git
cd speed_benchmark/
pip install -r requirements.txt
bash <(curl https://deb.openalpr.com/install)  # Select SDK
```

## Usage

1. View all command line options by running `python speed_benchmark.py -h`
2. Select your desired resolution(s) - `vga, 720p, 1080p, and/or 4k`
3. Benchmark using the default flags (1 stream and no minimum CPU threshold) by running `python speed_benchmark.py`
3. Check the average CPU utilization (see sample output below). Resolutions with a utilization less than 95% are bottlenecked 
on decoding the video stream (typical for higher resolutions). These should be rerun with additional streams for a 
better estimate of maximum performance
4. Set the `--thres` to a non-zero value. This causes the program to add streams until the threshold CPU utilization is 
achieved. We recommend using `90 < thres < 95`. On large systems where the CPU utilization for a single stream is much 
lower than your desired threshold, you can reduce the granularity of the search by setting `--steps > 1`
5. Estimate the number of cameras for a given total FPS value by using the following per-camera rules of thumb

* **Low Speed** (under 25 mph): 5-10 fps
* **Medium Speed** (25-45 mph): 10-15 fps
* **High Speed** (over 45 mph): 15-30 fps  

## Sample Output

Using default options

```commandline
user@ubuntu:~/git/speed-bench$ python speed_benchmark.py
Initializing...
	Operating system: Linux
	CPU model: Intel(R) Core(TM) i7-8750H CPU @ 2.20GHz
	Runtime data: /usr/share/openalpr/runtime_data
	OpenALPR configuration: /usr/share/openalpr/config/openalpr.defaults.conf
Downloading benchmark videos...
	Downloaded vga
	Downloaded 720p
	Downloaded 1080p
	Downloaded 4k
Testing with 1 stream(s)...
	Processing vga
	Processing 720p
	Processing 1080p
	Processing 4k
	Lowest average CPU usage 81.4%
+---------------------------------------------------------+
|        OpenALPR Speed: 1 stream(s) on 12 threads        |
+------------+-----------+-----------+-----------+--------+
| Resolution | Total FPS | CPU (Avg) | CPU (Max) | Frames |
+------------+-----------+-----------+-----------+--------+
|    vga     |    52.9   |    81.4   |    99.4   |  479   |
|    720p    |    49.6   |    84.9   |    99.5   |  479   |
|   1080p    |    44.4   |    88.8   |   100.0   |  479   |
|     4k     |    23.8   |    93.7   |   100.0   |  479   |
+------------+-----------+-----------+-----------+--------+
```

Starting with 3 streams and incrementing by 2 each time 95% CPU utilization is not achieved

```commandline
user@ubuntu:~/git/speed-bench$ python speed_benchmark.py --thres 95 --streams 3 --step 2
Initializing...
	Operating system: Linux
	CPU model: Intel(R) Core(TM) i7-8750H CPU @ 2.20GHz
	Runtime data: /usr/share/openalpr/runtime_data
	OpenALPR configuration: /usr/share/openalpr/config/openalpr.defaults.conf
Downloading benchmark videos...
	Found local vga
	Found local 720p
	Found local 1080p
	Found local 4k
Testing with 3 stream(s)...
	Processing vga
	Processing 720p
	Processing 1080p
	Processing 4k
	Lowest average CPU usage 93.2%
Testing with 5 stream(s)...
	Processing vga
	Processing 720p
	Processing 1080p
	Processing 4k
	Lowest average CPU usage 95.3%
+---------------------------------------------------------+
|        OpenALPR Speed: 5 stream(s) on 12 threads        |
+------------+-----------+-----------+-----------+--------+
| Resolution | Total FPS | CPU (Avg) | CPU (Max) | Frames |
+------------+-----------+-----------+-----------+--------+
|    vga     |    66.5   |    95.3   |   100.0   |  798   |
|    720p    |    61.3   |    96.2   |   100.0   |  798   |
|   1080p    |    54.1   |    97.3   |   100.0   |  798   |
|     4k     |    29.5   |    99.2   |   100.0   |  798   |
+------------+-----------+-----------+-----------+--------+
```
