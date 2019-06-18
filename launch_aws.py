from argparse import ArgumentParser
import json
import subprocess
from warnings import warn

ami = 'ami-024a64a6685d05041'  # Ubuntu 18.04 LTS 64-bit
key = 'aklinke'
instance = 'c4.large'
version = 'latest'


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

    # TODO tag instance Name from subprocess in get_flags()

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
        'user-data': setup}
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
    return ids, instance_types


def set_auto_terminate(ids):
    """Set instances to terminate on shutdown.

    :param [str] ids: List of instance IDs.
    :return: None
    """
    base = 'aws ec2 modify-instance-attribute '
    flags = '--instance-id {} --attribute instanceInitiatedShutdownBehavior --value terminate'
    for id in ids:
        cmd = base + flags.format(id)
        p = subprocess.Popen(cmd.split())
        exit_code = p.wait()
        if exit_code != 0:
            warn('Non-zero exit status when changing shutdown behavior for {}'.format(id))


if __name__ == '__main__':

    parser = ArgumentParser(description='Benchmark OpenALPR speed on AWS instances')
    parser.add_argument('-a', '--ami', type=str, default='ami-024a64a6685d05041', help='image for instances')
    parser.add_argument('-k', '--key', type=str, default='aklinke', help='name of key pair for SSH access')
    parser.add_argument('-v', '--version', type=str, required=True, help='either GA or latest OpenALPR')
    args = parser.parse_args()

    instances = [
        't2.large',
        'c5.9xlarge',
        'c4.large',
        'm5.2xlarge',
        'm5.4xlarge',
        't3a.large',
        't3.large',
        'x1e.xlarge',
        'z1d.large']
    print('Launching instances...')
    ids, types = launch_instances(args.ami, instances, args.key, args.version)
    for t, id in zip(types, ids):
        print('\t{}: {}'.format(t, id))
    print('Setting shutdown behavior to terminate...', end='\r')
    set_auto_terminate(ids)
    print('Setting shutdown behavior to terminate... Done')
