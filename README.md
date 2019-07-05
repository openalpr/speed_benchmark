# speed_benchmark 

Benchmark speed for various video resolutions on CPU or GPU

## Prequisites

* OpenALPR commercial license (2-week evaluation licenses can be obtained from 
[here](https://license.openalpr.com/evalrequest/))
* Ubuntu 18.04, Ubuntu 16.04, or Windows 10
* Python (2 or 3)

## Installation

**Generic**

1. Download the OpenALPR [SDK](http://doc.openalpr.com/sdk.html#installation) 
2. Clone this repository `git clone https://github.com/addisonklinke/openalpr-consulting.git`
3. Install the Python requirements `pip install -r requirements.txt`

**Docker**

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
3. Benchmark using the default flags (1 stream and no minimum processor utilization threshold)
3. Check the average processor utilization (see sample output below). Low utilization may indicate a bottleneck on 
decoding the video stream (typical for higher resolutions). These should be rerun with additional streams for a better 
estimate of maximum performance
4. Set the `--thres` to a non-zero value. This causes the program to add streams until the threshold processor 
utilization is achieved. We recommend using `90 < thres < 95` for CPU and `40 < thres < 60` for GPU. On large systems 
where the utilization for a single stream is much lower than your desired threshold, you can reduce the granularity of 
the search by setting `--steps > 1`
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
	Processing on CPU: Intel Core i7-8750H CPU @ 2.20GHz
	OpenALPR version: 2.7.101
	Runtime data: /usr/share/openalpr/runtime_data
	OpenALPR configuration: /usr/share/openalpr/config/openalpr.defaults.conf
Downloading benchmark videos...
	Found local vga
	Found local 720p
	Found local 1080p
	Found local 4k
Testing with 1 stream(s)...
	Processing vga
	Processing 720p
	Processing 1080p
	Processing 4k
	Lowest average processor utilization 77.2%
+-------------------------------------------------------------------------+
|                OpenALPR Speed: 1 stream(s) on 12 threads                |
+------------+-----------+-------------------+-------------------+--------+
| Resolution | Total FPS | Processor (Avg %) | Processor (Max %) | Frames |
+------------+-----------+-------------------+-------------------+--------+
|    vga     |    64.2   |        77.2       |        99.0       |  479   |
|    720p    |    57.5   |        81.0       |       100.0       |  479   |
|   1080p    |    52.1   |        85.6       |       100.0       |  479   |
|     4k     |    30.4   |        92.7       |        99.7       |  479   |
+------------+-----------+-------------------+-------------------+--------+
```

Starting with 3 streams and incrementing by 2 each time 95% CPU utilization is achieved

```commandline
user@ubuntu:~/git/speed-bench$ python speed_benchmark.py --thres 95 --streams 3 --step 2
Initializing...
	Operating system: Linux
	Processing on CPU: Intel Core i7-8750H CPU @ 2.20GHz
	OpenALPR version: 2.7.101
	Runtime data: /usr/share/openalpr/runtime_data
	OpenALPR configuration: /usr/share/openalpr/config/openalpr.defaults.conf
Downloading benchmark videos...
	Downloaded vga
	Downloaded 720p
	Downloaded 1080p
	Downloaded 4k
Testing with 3 stream(s)...
	Processing vga
	Processing 720p
	Processing 1080p
	Processing 4k
	Lowest average processor utilization 91.9%
Testing with 5 stream(s)...
	Processing vga
	Processing 720p
	Processing 1080p
	Processing 4k
	Lowest average processor utilization 95.9%
+-------------------------------------------------------------------------+
|                OpenALPR Speed: 7 stream(s) on 12 threads                |
+------------+-----------+-------------------+-------------------+--------+
| Resolution | Total FPS | Processor (Avg %) | Processor (Max %) | Frames |
+------------+-----------+-------------------+-------------------+--------+
|    vga     |    74.1   |        95.9       |       100.0       |  479   |
|    720p    |    68.9   |        96.6       |       100.0       |  479   |
|   1080p    |    58.8   |        97.4       |       100.0       |  479   |
|     4k     |    33.0   |        98.9       |       100.0       |  479   |
+------------+-----------+-------------------+-------------------+--------+
```
