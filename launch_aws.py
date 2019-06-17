from argparse import ArgumentParser
import json
import subprocess

# TODO add feedback loop to benchmark script to determine appropriate number of cores
# TODO run nginx server on instances, write results to public
# TODO query HTTP from Python and terminate instance once results are available
# TODO tag instance Name from subprocess in get_flags()

ami = 'ami-024a64a6685d05041'  # Ubuntu 18.04 LTS 64-bit
instances = {
    'c5.9xlarge': {'cores': 18, 'cpu': 'Intel Xeon Platinum 8124M @ 3.0 GHz'},
    'c4.large': {'cores': 1, 'cpu': 'Intel Xeon E5-2666 v3 @ 2.9 GHz'},
    'm5.2xlarge': {'cores': 4, 'cpu': 'Intel Xeon Platinum 8175M @ 2.5 GHz'},
    'm5.4xlarge': {'cores': 4, 'cpu': 'Intel Xeon Platinum 8175M @ 2.5 GHz'},
    't2.large': {'cores': 1, 'cpu': 'Intel Xeon E5-2686 v4 @ 2.3 GHz'},
    't3a.large': {'cores': 2, 'cpu': 'AMD EPYC 7571 @ 2.2 GHz'},
    't3.large': {'cores': 1, 'cpu': 'Intel Xeon Platinum 8175M @ 2.5 GHz'},
    'x1e.xlarge': {'cores': 2, 'cpu': 'Intel Xeon E7-8880 v3 @ 2.3 GHz'},
    'z1d.large': {'cores': 1, 'cpu': 'Intel Xeon Platinum 8151 @ 3.4 GHz'}}


def get_flags(ami, instance_type, key, version):
    """Format command line flags for AWS CLI.

    Output from the startup script is viewable on instance at
    ``/var/log/cloud-init-output.log``. The raw script itself is also stored
    at ``/var/lib/cloud/instances/[instance-id]/user-data.txt``.

    :param str ami: Image for instance.
    :param str instance_type: Type of AWS instance (i.e. t2.micro).
    :param str key: Name of key pair to assign to instance for SSH access.
    :param str version: Either GA or latest OpenALPR.
    :return str flags:
    """
    if version == 'GA':
        setup = 'file://aws_setup_ga.sh'
    elif version == 'latest':
        setup = 'file://aws_setup_latest.sh'
    else:
        raise ValueError('Version must be GA or latest, received {}'.format(version))
    params = {
        'image-id': ami,
        'instance-type': instance_type,
        'key-name': key,
        'user-data': setup,
        'security-group-ids': 'sg-01463e7f4849905ee'}
    flags = '--' + ' --'.join(['{} {}'.format(k, v) if v is not None else k for k, v in params.items()])
    return flags


def launch_instances(ami, instance_types, key, version):
    """Allocate EC2 instances.

    :param str ami: Image for instance.
    :param [str] instance_types: List of AWS instance types (i.e. t2.micro).
    :param str key: Name of key pair to assign to instance for SSH access.
    :param str version: Either GA or latest OpenALPR.
    :return [str] ids:
    """
    ids = []
    for instance in instance_types:
        cmd = 'aws ec2 run-instances {}'.format(get_flags(ami, instance, key, version))
        out = subprocess.check_output(cmd.split())
        response = json.loads(out)
        ids.append(response['Instances'][0]['InstanceId'])
    return ids


if __name__ == '__main__':

    parser = ArgumentParser(description='Benchmark OpenALPR speed on AWS instances')
    parser.add_argument('-a', '--ami', type=str, default='ami-024a64a6685d05041', help='image for instances')
    parser.add_argument('-k', '--key', type=str, default='aklinke', help='name of key pair for SSH access')
    parser.add_argument('-v', '--version', type=str, required=True, help='either GA or latest OpenALPR')
    args = parser.parse_args()

    ids = launch_instances(args.ami, instances, args.key)
