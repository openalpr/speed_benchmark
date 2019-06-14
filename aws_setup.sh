#!/bin/bash

# Setup Docker container and clone benchmark repository ----------------------
export DEBIAN_FRONTEND=noninteractive
apt update; apt install -y docker.io
docker run --rm -v /etc/openalpr:/etc/openalpr/ -it openalpr/commercial-agent /bin/bash
apt update; apt install -y curl python-pip git
git clone https://github.com/openalpr/speed_benchmark.git
cd speed_benchmark
pip install -r requirements.txt

# Install OpenALPR SDK -------------------------------------------------------
curl -L https://deb.openalpr.com/openalpr.gpg.key | apt-key add -
echo 'deb https://deb.openalpr.com/xenial-commercial/ xenial main' | tee /etc/apt/sources.list.d/openalpr.list
packages="openalpr python-openalpr python-alprstream python-vehicleclassifier"
apt install -y apt-transport-https
apt update; apt install -o apt::install-recommends=true -y ${packages}
rm /etc/apt/sources.list.d/openalpr.list
key="SEpKS0xNTk6wsbKztLXHw8zA2cTCoNvNxd/GxqWgoKKoq6mqq6yvqpaUkpGXlJGWARfsUaP0ezh137atA4RZWBOoW7LCK9IsjMgJnSGPPdl7Er/\
a8nfNIQ5fTX4xGAMBgQFrGdXvcQNkcZxZ5AYBa2J7vFM+/uyKMRvbL7bmjf/AqkkkJ7kG8MbZTenzQbrw"
echo ${key} | tee /etc/openalpr/license.conf

# Run speed benchmark --------------------------------------------------------
python speed_benchmark.py
