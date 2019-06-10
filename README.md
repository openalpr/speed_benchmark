# speed_benchmark 

Drive OpenALPR on all CPU cores to benchmark speed for various video resolutions

## Prequisites

* OpenALPR commercial license (2-week evaluation licenses can be obtained from 
[here](https://license.openalpr.com/evalrequest/))
* Ubuntu 18.04, Ubuntu 16.04, or Windows 10
* Python3

## Installation

1. Download the OpenALPR [SDK](http://doc.openalpr.com/sdk.html#installation) 
2. Clone this repository `git clone https://github.com/addisonklinke/openalpr-consulting.git`
3. Install the Python requirements `pip install -r requirements.txt`

## Usage

1. View all command line options by running `python speed_benchmark.py -h`
2. Select your desired resolution(s) and run a benchmark with 1 stream. Options are `vga, 720p, 1080p, and 4k`
3. Check the average CPU utilization in the output. Resolutions with a utilization less than 95% are bottlenecked on
decoding the video stream (typical for higher resolutions). These should be rerun with additional streams for a 
better estimate of maximum performance using the `--streams` flag

## Sample Output

```commandline
user@ubuntu:~/openalpr-consulting/speed-bench$ python speed_benchmark.py --streams 4
Initializing...
	Operating system: Linux
	CPU model: Intel(R) Core(TM) i7-8750H CPU @ 2.20GHz
	Runtime data: /usr/share/openalpr/runtime_data
	OpenALPR configuration: /usr/share/openalpr/config/openalpr.defaults.conf
Downloading benchmark videos...
	Found local vga
	Downloaded 720p
	Found local 1080p
	Found local 4k
Processing vga...
Processing 720p...
Processing 1080p...
Processing 4k...
+---------------------------------------------------------+
|      OpenALPR Benchmark: 4 stream(s) on 12 threads      |
+------------+-----------+-----------+-----------+--------+
| Resolution | Total FPS | CPU (Avg) | CPU (Max) | Frames |
+------------+-----------+-----------+-----------+--------+
|    vga     |    89.7   |    98.6   |   100.0   | 10978  |
|    720p    |    68.7   |    98.2   |   100.0   |  1125  |
|   1080p    |    43.2   |    97.5   |   100.0   |  600   |
|     4k     |    36.2   |    99.5   |   100.0   |  870   |
+------------+-----------+-----------+-----------+--------+
```

To estimate the number of cameras for a given total FPS value, use the following per-camera rules of thumb

* **Low Speed** (under 25 mph): 5-10 fps
* **Medium Speed** (25-45 mph): 10-15 fps
* **High Speed** (over 45 mph): 15-30 fps

## Running in Docker

If preferred, you can install OpenALPR software in our pre-built Docker container

```bash
docker run -d -P -v openalpr-vol1-config:/etc/openalpr/ -v openalpr-vol1-images:/var/lib/openalpr/ -it openalpr/commercial-agent
docker exec -it <container> /bin/bash
apt update && apt install -y curl python-pip git
git clone https://github.com/addisonklinke/openalpr-consulting.git
cd openalpr-consulting/speed-bench
pip install -r requirements.txt
bash <(curl https://deb.openalpr.com/install)  # Select SDK
```
