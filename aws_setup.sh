#!/bin/bash

# Clone benchmark repository and install requirements ------------------------
printf "\nInstalling apt dependencies and cloning repository...\n"
export DEBIAN_FRONTEND=noninteractive
apt update; apt install -y curl python-pip git
git clone https://github.com/openalpr/speed_benchmark.git
cd speed_benchmark
pip install -r requirements.txt

# Install OpenALPR SDK -------------------------------------------------------
printf "\nInstalling OpenALPR SDK...\n"
curl -L https://deb.openalpr.com/openalpr.gpg.key |  apt-key add -
echo 'deb https://deb.openalpr.com/bionic/ bionic main' |  tee /etc/apt/sources.list.d/openalpr.list
packages="openalpr python-openalpr python-alprstream python-vehicleclassifier"
apt update; apt install -o apt::install-recommends=true -y ${packages}
key="SEpKS0xNTk6wsbKztLXHw8zA2cTCoNvNxd/GxqWgoKKoq6mqq6yvqpaUkpGXlJGWARfsUaP0ezh137atA4RZWBOoW7LCK9IsjMgJnSGPPdl7Er/\
a8nfNIQ5fTX4xGAMBgQFrGdXvcQNkcZxZ5AYBa2J7vFM+/uyKMRvbL7bmjf/AqkkkJ7kG8MbZTenzQbrw"
echo ${key} | tee /etc/openalpr/license.conf

# Run speed benchmark --------------------------------------------------------
printf "\nRunning speed benchmarks... "
python -u speed_benchmark.py > /tmp/speed.txt
echo "Done"
