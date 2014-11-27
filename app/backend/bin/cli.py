import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import logging
import traceback
import json
import re

from backendservice import backendservices
from utils import dynamodb

def get_aws_credentials():
    if not os.environ.has_key("AWS_ACCESS_KEY_ID") or not os.environ.has_key("AWS_SECRET_ACCESS_KEY"):
        raise "Environment variables AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are not set!"

    return { 'AWS_ACCESS_KEY_ID': os.environ["AWS_ACCESS_KEY_ID"],
             'AWS_SECRET_ACCESS_KEY': os.environ["AWS_SECRET_ACCESS_KEY"]}

class UnsupportedError(BaseException):
    pass

class InvalidConfigurationError(BaseException):
    pass

class BackendCli:
    SUPPORTED_OUTPUT_STORES = ["amazon_s3"]
    SUPPORTED_JOB_STATUS_DB_STORES = ["amazon_dynamodb"]

    def __init__(self, cli_jobs_config):
        self.backend = backendservices(cli_mode=True)

        self.machines = cli_jobs_config["machines"]
        self.jobs = cli_jobs_config["jobs"]

        if cli_jobs_config["output_store"]["type"] not in self.SUPPORTED_OUTPUT_STORES:
            raise UnsupportedError("Output store {0} not supported !".format(cli_jobs_config["output_store"]["type"]))

        if cli_jobs_config["job_status_db_store"]["type"] not in self.SUPPORTED_JOB_STATUS_DB_STORES:
            raise UnsupportedError("Job Status DB store {0} not supported !".format(
                                                        cli_jobs_config["job_status_db_store"]["type"]))

        if re.match('^amazon.*', cli_jobs_config["output_store"]["type"]) or \
                            re.match('^amazon.*', cli_jobs_config["job_status_db_store"]["type"]):
            self.aws_credentials = get_aws_credentials()

        self.output_store_info = cli_jobs_config["output_store"]
        self.job_status_db_store_info = cli_jobs_config["job_status_db_store"]

    def run(self):
        print dynamodb.create_table(self.job_status_db_store_info['table_name'])

        self.prepare_machines()

        for index, job in enumerate(self.jobs):
            logging.info("Preparing for  Job #{0}...".format(index))
            with open(job['model_file_path']) as xml_file:
                model_xml_doc = xml_file.read()

            params = {}
            params['paramstring'] = job['paramstring']
            params['document'] = model_xml_doc
            params['job_type'] = job['job_type']
            params['bucketname'] = self.output_store_info['bucket_name']

            self.backend.execute_task(params)
            logging.info("Job #{0} submitted to backend.".format(index))

    def get_preparing_commands(self):
        # These are commutative commands

        commands = []
        # commands.append("set -x")
        # commands.append("exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1")
        # commands.append("touch anand3.txt")
        # commands.append("echo testing logfile")
        # commands.append("echo BEGIN")
        # commands.append("date '+%Y-%m-%d %H:%M:%S'")
        # commands.append("echo END")
        # commands.append("touch anand2.txt")

        commands.append('export AWS_ACCESS_KEY_ID={0}'.format(self.aws_credentials['AWS_ACCESS_KEY_ID']))
        commands.append('export AWS_SECRET_ACCESS_KEY={0}'.format(self.aws_credentials['AWS_SECRET_ACCESS_KEY']))

        commands.append('echo export AWS_ACCESS_KEY_ID={0} >> ~/.bashrc'.format(self.aws_credentials['AWS_ACCESS_KEY_ID']))
        commands.append('echo export AWS_SECRET_ACCESS_KEY={0} >> ~/.bashrc'.format(self.aws_credentials['AWS_SECRET_ACCESS_KEY']))

        # commands.append('echo export AWS_ACCESS_KEY_ID={0} >> /home/ubuntu/.bashrc'.format(str(self.aws_credentials['AWS_ACCESS_KEY_ID'])))
        # commands.append('echo export AWS_SECRET_ACCESS_KEY={0} >> /home/ubuntu/.bashrc'.format(self.aws_credentials['AWS_SECRET_ACCESS_KEY']))

        commands.append('export STOCHKIT_HOME={0}'.format('/home/ubuntu/stochss/StochKit/'))
        commands.append('export STOCHKIT_ODE={0}'.format('/home/ubuntu/stochss/ode/'))

        commands.append('echo export STOCHKIT_HOME={0} >> ~/.bashrc'.format("/home/ubuntu/stochss/StochKit/"))
        commands.append('echo export STOCHKIT_ODE={0} >> ~/.bashrc'.format("/home/ubuntu/stochss/ode/"))

        commands.append('echo export C_FORCE_ROOT=1 >> ~/.bashrc')
        # commands.append('echo export C_FORCE_ROOT=1 >> /home/ubuntu/.bashrc')

        commands.append('source ~/.bashrc')

        return commands

    def prepare_machines(self):
        logging.debug("prepare_machines: inside method with machine_info : %s", str(self.machines))

        queue_head = None
        slave_machines = []
        for machine in self.machines:
            if machine["type"] == "queue-head":
                if queue_head is not None:
                    raise InvalidConfigurationError("There can be only one master !")
                else:
                    queue_head = machine
            elif machine["type"] == "worker":
                slave_machines.append(machine)
            else:
                raise InvalidConfigurationError("Invalid machine type : {0} !".format(machine["type"]))
        if queue_head == None:
            raise InvalidConfigurationError("Need at least one master!")

        try:
            self.backend.__update_celery_config_with_queue_head_ip(queue_head_ip=queue_head["ip"])
            logging.info("Updated celery config with queue head ip: {0}".format(queue_head["ip"]))

            for machine in self.machines:
                self.__copy_celery_config_to_machine(user=machine["user"],
                                                     ip=machine["ip"],
                                                     key_file_path=machine["key_file_path"])

                self.__start_celery_on_machine_via_ssh(user=machine["user"],
                                                       ip=machine["ip"],
                                                       key_file_path=machine["key_file_path"])

            commands = self.get_preparing_commands()

            command = ';'.join(commands)
            for machine in self.machines:
                if machine['type'] == 'queue-head':
                    rabbitmq_commands = []
                    rabbitmq_commands.append('sudo rabbitmqctl add_user stochss ucsb')
                    rabbitmq_commands.append('sudo rabbitmqctl set_permissions -p / stochss \\\".*\\\" \\\".*\\\" \\\".*\\\"')

                    logging.debug("Adding RabbitMQ commands...")
                    updated_command = ';'.join(commands + rabbitmq_commands)

                    remote_command = "ssh -o 'StrictHostKeyChecking no' -i {key_file} {user}@{ip} \"{cmd}\"".format(
                                                                                    key_file=machine["key_file_path"],
                                                                                    user=machine["user"],
                                                                                    ip=machine["ip"],
                                                                                    cmd=updated_command)
                else:
                    remote_command = "ssh -o 'StrictHostKeyChecking no' -i {key_file} {user}@{ip} \"{cmd}\"".format(
                                                                                    key_file=machine["key_file_path"],
                                                                                    user=machine["user"],
                                                                                    ip=machine["ip"],
                                                                                    cmd=command)

                logging.debug("Remote command: {0}".format(remote_command))
                os.system(remote_command)

            return { "success": True }

        except Exception, e:
            traceback.print_exc()
            logging.error("prepare_machines : exiting method with error : {0}".format(str(e)))
            return None


    def __start_celery_on_machine_via_ssh(self, user, ip, key_file_path):
        print 'inside __start_celery_on_machine_via_ssh'

        commands = []
        commands.append('source /home/ubuntu/.bashrc')
        commands.append('export PYTHONPATH=/home/ubuntu/pyurdme/:/home/ubuntu/stochss/app/:/home/ubuntu/stochss/app/backend')
        commands.append('export AWS_ACCESS_KEY_ID={0}'.format(self.aws_credentials['AWS_ACCESS_KEY_ID']))
        commands.append('export AWS_SECRET_ACCESS_KEY={0}'.format(self.aws_credentials['AWS_SECRET_ACCESS_KEY']))
        commands.append('celery -A tasks worker --autoreload --loglevel=info --workdir /home/ubuntu > /home/ubuntu/celery.log 2>&1')

        # PyURDME must be run inside a 'screen' terminal as part of the FEniCS code depends on the ability to write to
        # the process' terminal, screen provides this terminal.
        celery_cmd = "sudo screen -d -m bash -c '{0}'\n".format(';'.join(commands))

        logging.info("keyfile = {0}".format(key_file_path))

        if not os.path.exists(key_file_path):
            raise Exception("ssh keyfile file not found: {0}".format(key_file_path))

        command = "ssh -o 'StrictHostKeyChecking no' -i {key_file_path} {user}@{ip} \"{cmd}\"".format(key_file_path=key_file_path,
                                                                                               user=user,
                                                                                               ip=ip,
                                                                                               cmd=celery_cmd)
        logging.info(command)
        success = os.system(command)

        if success == 0:
            logging.info("celery started on {0}".format(ip))
        else:
            raise Exception("Failure to start celery on {0}".format(ip))


    def __copy_celery_config_to_machine(self, user, ip, key_file_path):
        logging.debug("keyfile = {0}".format(key_file_path))

        if not os.path.exists(key_file_path):
            raise Exception("ssh keyfile file not found: {0}".format(key_file_path))

        celery_config_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "conf", "celeryconfig.py")
        logging.debug("celery_config_filename = {0}".format(celery_config_filename))

        if not os.path.exists(celery_config_filename):
            raise Exception("celery config file not found: {0}".format(celery_config_filename))

        cmd = "scp -o 'StrictHostKeyChecking no' -i {key_file_path} {file} {user}@{ip}:celeryconfig.py".format(
                                                                                            key_file_path=key_file_path,
                                                                                            file=celery_config_filename,
                                                                                            user=user,
                                                                                            ip=ip)
        logging.info(cmd)

        success = os.system(cmd)
        if success == 0:
            logging.info("scp success: {0} transfered to {1}".format(celery_config_filename, ip))
        else:
            raise Exception("scp failure: {0} not transfered to {1}".format(celery_config_filename, ip))

if __name__ == "__main__":
    # logging.basicConfig(filename='testoutput.log', filemode='w', level=logging.DEBUG)
    logging.basicConfig(level=logging.DEBUG)

    if len(sys.argv) < 2:
        cli_jobs_config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'conf', 'cli_jobs_config.json')
        print cli_jobs_config_file

    else:
        cli_jobs_config_file = sys.argv[1]
        if not os.path.exists(cli_jobs_config_file):
            raise Exception('Invalid cli jobs config file given!')

    with open(cli_jobs_config_file) as file:
        cli_jobs_config = json.loads(file.read())

    cli = BackendCli(cli_jobs_config)
    cli.run()