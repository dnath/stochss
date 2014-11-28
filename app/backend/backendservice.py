'''
This class exposes all the services offered by the backend
It accepts calls from the front-end and pass them on to the backend.
All the input validation is performed in this class.
'''
from infrastructure_manager import InfrastructureManager
import threading
import os, subprocess, shlex, signal, uuid, sys, time
import logging, traceback
from datetime import datetime
import pprint

from tasks import *
from utils import dynamodb

import boto
from boto.s3.connection import S3Connection

import celery
from celery.task.control import inspect


class backendservices():
    ''' 
    constructor for the backend service class.
    It should be passed the agent creds
    ''' 
        
    # Class Constants
    TABLE_NAME = 'stochss'
    KEY_PREFIX = 'stochss'
    QUEUE_HEAD_KEY_TAG = 'queuehead'
    INFRA_EC2 = 'ec2'
    INFRA_CLUSTER = 'cluster'
    WORKER_AMIS = {
        INFRA_EC2: 'ami-e0ad3288'
    }

    def __init__(self, **kwargs):
        '''
        constructor to set the path of various libraries
        '''
        self.cli_mode = kwargs["cli_mode"] if kwargs.has_key("cli_mode") else False

        sys.path.append(os.path.join(os.path.dirname(__file__), 'lib/boto'))
        sys.path.append(os.path.join(os.path.dirname(__file__), 'lib/celery'))
        sys.path.append(os.path.join(os.path.dirname(__file__), 
                                     '/Library/Python/2.7/site-packages/amqp'))

    def __is_queue_broker_up(self):
        sleep_time = 5
        total_wait_time = 15
        total_tries = total_wait_time / sleep_time

        current_try = 0
        broker_url = celery.current_app.conf['BROKER_URL']
        logging.info("About to check broker at: {0}".format(broker_url))

        while True:
            try:
                inspection_stats = inspect().stats()

            except IOError as e:
                current_try += 1
                logging.info("Broker down, try: {0}, exception: {1}".format(current_try, e))

                if current_try >= total_tries:
                    logging.info("Broker unreachable for {0} seconds.".format(total_wait_time))
                    return False, e, traceback.format_exc()

                time.sleep(sleep_time)
                continue

            logging.info("Broker up")
            break

        return True, None, None
            
    def execute_task(self, params):
        '''
        This method instantiates celery tasks in the cloud.
        Returns return value from celery async call and the task ID
        '''
        logging.debug("params = \n{0}".format(pprint.pformat(params)))
        result = {}
        try:
            #This is a celery task in tasks.py: @celery.task(name='stochss')

            # Need to make sure that the queue is actually reachable because
            # we don't want the user to try to submit a task and have it
            # timeout because the broker server isn't up yet.

            is_broker_up, exception, traceback_str = self.__is_queue_broker_up()
            if is_broker_up is False:
                return {
                    "success": False,
                    "reason": "Cloud instances unavailable. Please wait a minute for their initialization to complete.",
                    "exception": str(exception),
                    "traceback": traceback_str
                }

            task_id = str(uuid.uuid4())
            logging.debug("task_id = {0}".format(task_id))
            result["db_id"] = task_id

            #create a celery task
            logging.info("executeTask : executing task with uuid : %s ", task_id)
            time_now = datetime.now()
            data = {
                'status': "pending",
                "start_time": time_now.strftime('%Y-%m-%d %H:%M:%S'),
                'Message': "Task sent to Cloud"
            }
            
            tmp = None
            if params["job_type"] == "mcem2":
                queue_name = task_id
                result["queue"] = queue_name
                data["queue"] = queue_name

                # How many cores?
                requested_cores = -1
                if "cores" in params:
                    requested_cores = int(params["cores"])
                
                ##################################################################################################################
                # The master task can run on any node...
                # TODO: master task might need to run on node with at least 2 cores...
                # launch_params["instance_type"] = "c3.large"
                # launch_params["num_vms"] = 1
                ##################################################################################################################
                
                celery_info = CelerySingleton().app.control.inspect()

                # How many active workers are there?
                active_workers = celery_info.active()

                # We will keep around a dictionary of the available workers, where
                # the key will be the workers name and the value will be how many
                # cores that worker has (i.e. how many tasks they can execute 
                # concurrently).
                available_workers = {}
                core_count = 0

                if active_workers:
                    for worker_name in active_workers:
                        # active_workers[worker_name] will be a list of dictionaries representing
                        # tasks that the worker is currently executing, so if it doesn't exist
                        # then the worker isn't busy
                        if not active_workers[worker_name]:
                            available_workers[worker_name] = celery_info.stats()[worker_name]['pool']['max-concurrency']
                            core_count += int(available_workers[worker_name])

                logging.info("All available workers:".format(available_workers))

                # We assume that at least one worker is already consuming from the main queue
                # so we just need to find that one worker and remove it from the list, since
                # we need one worker on the main queue for the master task.
                done = False
                for worker_name in available_workers:
                    worker_queues = celery_info.active_queues()[worker_name]

                    for queue in worker_queues:
                        if queue["name"] == "celery":
                            popped_cores = int(available_workers.pop(worker_name))
                            done = True
                            core_count -= popped_cores
                            break

                    if done:
                        break

                if core_count <= 0:
                    # Then there's only one worker available
                    return {
                        "success": False,
                        "reason": "You need to have at least two workers in order to run a parameter estimation job in the cloud."
                    }

                logging.info("Found {0} cores that can be used as slaves on the following workers: {1}".format(core_count,
                                                                                                               available_workers))
                if requested_cores == -1:
                    params["paramstring"] += " --cores {0}".format(core_count)
                    # Now just use all available cores since the user didn't request
                    # a specific amount, i.e. re-route active workers to the new queue
                    worker_names = []
                    for worker_name in available_workers:
                        worker_names.append(worker_name)
                    logging.info("Rerouting all available workers: {0} to queue: {1}".format(worker_names, queue_name))
                    reroute_workers(worker_names, queue_name)

                else:
                    params["paramstring"] += " --cores {0}".format(requested_cores)
                    # Now loop through available workers and see if we have enough free to meet
                    # requested core count.
                    worker_names = []
                    unmatched_cores = requested_cores

                    if available_workers:
                        for worker_name in available_workers:
                            # We need to find out what the concurrency of the worker is.
                            worker_cores = available_workers[worker_name]
                            # Subtract this from our running count and save the workers name
                            unmatched_cores -= worker_cores
                            worker_names.append(worker_name)
                            if unmatched_cores <= 0:
                                # Then we have enough
                                break

                    # Did we get enough?
                    if unmatched_cores > 0:
                        # Nope...
                        return {
                            "success": False,
                            "reason": "Didn't find enough idle cores to meet requested core count of {0}. Still need {1} more.".format(
                                requested_cores,
                                unmatched_cores
                            )
                        }

                    logging.info("Found enough idle cores to meet requested core count of {0}".format(requested_cores))

                    # We have enough, re-route active workers to the new queue
                    logging.info("Rerouting workers: {0} to queue: {1}".format(worker_names, queue_name))
                    reroute_workers(worker_names, queue_name)
                
                # Update DB entry just before sending to worker
                dynamodb.update_entry(task_id, data, backendservices.TABLE_NAME)
                params["queue"] = queue_name
                tmp = master_task.delay(task_id, params)

                # TODO: This should really be done as a background_thread as soon as the task is sent
                #      to a worker, but this would require an update to GAE SDK.
                # call the poll task process

                poll_task_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poll_task.py")
                logging.info("Task sent to cloud with celery id {0}...".format(tmp.id))

                poll_task_string = "python {0} {1} {2} > poll_task_{1}.log 2>&1".format(poll_task_path,
                                                                                        tmp.id,
                                                                                        queue_name)
                p = subprocess.Popen(shlex.split(poll_task_string))
                result["celery_pid"] = tmp.id

            else:
                dynamodb.update_entry(task_id, data, backendservices.TABLE_NAME)
                #celery async task execution http://ask.github.io/celery/userguide/executing.html
                tmp = task.delay(task_id, params)  #calls task(taskid,params)
                result["celery_pid"] = tmp.id

            logging.info("executeTask :  result of task : %s", str(tmp))
            result["success"] = True
            return result

        except Exception, e:
            logging.error("executeTask : error - %s", str(e))
            return {
                "success": False,
                "reason": str(e),
                "exception": str(e),
                "traceback": traceback.format_exc()
            }

    def execute_local_task(self, params):
        '''
        This method spawns a stochkit process. It doesn't wait for the process to finish. The status of the
        process can be tracked using the pid and the output directory returned by this method. 
        
        @param  params['document'] = the contents of the xml file 
        @param  params['paramstring'] = the parameter to be passed to the stochkit execution
        'STOCHKIT_HOME' = this is the environment variable which has the path of the stochkit executable
        @return: 
           {"pid" : 'the process id of the task spawned', "output": "the directory where the files will be generated"}
         
        '''
        try:           
            logging.info("execute_local_task : inside method with params : \n%s ", pprint.pformat(params))
            res = {}
            
            paramstr =  params['paramstring']
            uuidstr = str(uuid.uuid4())
            res['uuid'] = uuidstr
            create_dir_str = "mkdir -p output/%s " % uuidstr
            os.system(create_dir_str)
            
            # Write the model document to file
            xml_file_path = os.path.join("output", uuidstr, uuidstr + ".xml")
            xml_file_path = os.path.abspath(xml_file_path)

            model_fhandle = open(xml_file_path, 'w')
            model_fhandle.write(params['document'])
            model_fhandle.close()
            
            # Pipe output to these files
            res['stdout'] = os.path.abspath(os.path.join('output', uuidstr, 'stdout'))
            res['stderr'] = os.path.abspath(os.path.join('output', uuidstr, 'stderr'))

            backend_dir = os.path.abspath(os.path.dirname(__file__))
            # The following executiong string is of the form :
            # stochkit_exec_str = "ssa -m ~/output/%s/dimer_decay.xml -t 20 -i 10 -r 1000" % (uuidstr)
            stochkit_exec_str = "{backend_dir}/wrapper.py {stdout} {stderr} {0} --model {1} --out-dir output/{2}/result ".format(paramstr,
                                                                                                                                xml_file_path,
                                                                                                                                uuidstr,
                                                                                                                                stdout=res['stdout'],
                                                                                                                                stderr=res['stderr'],
                                                                                                                                backend_dir=backend_dir)
            print stochkit_exec_str
            logging.info("STOCHKIT_EXEX_STR: " + stochkit_exec_str)
            logging.debug("execute_local_task: Spawning StochKit Task. String : %s", stochkit_exec_str)
            
            p = subprocess.Popen(stochkit_exec_str.split(), stdin=subprocess.PIPE)

            #logging.debug("execute_local_task: the result of task {0} or error {1} ".format(output,error))
            pid = p.pid

            res['pid'] = pid
            filepath = "output/%s//" % (uuidstr)
            logging.debug("execute_local_task : PID generated - %s", pid)
            absolute_file_path = os.path.abspath(filepath)

            logging.debug("execute_local_task : Output file - %s", absolute_file_path)
            res['output'] = absolute_file_path

            logging.info("execute_local_task: exiting with result : %s", str(res))
            return res

        except Exception as e:
            logging.error("execute_local_task : exception raised : %s" , str(e))
            return None

    def check_local_task_status(self, pids):
        '''
        checks the status of the pids and returns true if the task is running or else returns false
        pids = [list of pids to check for status]
        returns a dictionary as {"pid1":"status", "pid2":"status", "pid3":"status"}
        '''
        res = {}
        logging.info("check_local_task_status : inside with params {0}".format(pids))

        try:
            for pid in pids:
                try:
                    os.kill(pid, 0)
                    res[pid] = True
                except Exception,e:
                    res[pid] = False

            logging.info("check_local_task_status : exiting with result : {0}".format(res))
            return res

        except Exception as e:
            logging.error("check_local_task_status: Exiting with error : {0}".format(e))
            return None
    
    def check_cloud_task_status(self, pids):
        '''
        checks the status of the pids and returns true if the task is running or else returns false
        pids = [list of pids to check for status]
        returns a dictionary as {"pid1":"status", "pid2":"status", "pid3":"status"}
        '''
        res = {}
        
        return res

    def describe_task(self, params):
        '''
        @param params: A dictionary with the following fields
         "AWS_ACCESS_KEY_ID" : AWS access key
         "AWS_SECRET_ACCESS_KEY": AWS security key
         taskids : list of celery taskids
         @return: 
         a dictionary of the form :
         {"taskid":"result:"","state":""} 
        '''
        os.environ["AWS_ACCESS_KEY_ID"] = params['AWS_ACCESS_KEY_ID']
        os.environ["AWS_SECRET_ACCESS_KEY"] = params['AWS_SECRET_ACCESS_KEY']

        logging.debug("describe_task: setting environment variables : AWS_ACCESS_KEY_ID = %s", params['AWS_ACCESS_KEY_ID'])
        logging.debug("describe_task: setting environment variables : AWS_SECRET_ACCESS_KEY = %s", params['AWS_SECRET_ACCESS_KEY'])

        result = {}
        try:
            result = dynamodb.describe_task(params['taskids'], backendservices.TABLE_NAME)
        except Exception, e:
            logging.error("describe_task : exiting with error : %s", str(e))
            return None

        return result
    
    def stop_tasks(self, params):
        '''
        @param id_pairs: a list of (database_id, task_id) pairs, each representing
                          a task to be stopped
        '''
        credentials = params['credentials']
        id_pairs = params['ids']

        # First we need to stop the workers from working on the tasks
        db_ids = []
        for id_pair in id_pairs:
            task_id = id_pair[0]
            database_id = id_pair[1]
            logging.info("stopTasks calling removeTask('{0}')".format(task_id))
            remove_task(task_id)
            db_ids.append(database_id)

        # Then we need to return the final description of the tasks
        describe_params = {
            'AWS_ACCESS_KEY_ID': credentials['AWS_ACCESS_KEY_ID'],
            'AWS_SECRET_ACCESS_KEY': credentials['AWS_SECRET_ACCESS_KEY'],
            'taskids': db_ids
        }

        return self.describe_task(describe_params)
    
    def delete_tasks(self, taskids):
        '''
        @param taskid:the list of taskids to be removed 
        this method revokes scheduled tasks as well as the tasks in progress. It 
        also removes task from the database. It ignores the taskids which are not active.
        '''
        logging.info("delete_tasks : inside method with taskids : %s", taskids)
        try:
            for taskid_pair in taskids:
                print 'delete_tasks: removing task {0}'.format(str(taskid_pair))
                # this removes task from celery queue
                remove_task(taskid_pair[0])

                # this removes task information from DB.
                dynamodb.remove_task(backendservices.TABLE_NAME, taskid_pair[1])

            logging.info("delete_tasks: All tasks removed")

        except Exception, e:
            logging.error("delete_tasks : exiting with error : %s", str(e))
    
    def delete_local_task(self, pids):
        """
        pids : list of pids to be deleted.
        Terminates the processes associated with the PID. 
        This methods ignores the PID which are  not active.
        """
        logging.info("deleteTaskLocal : inside method with pids : %s", pids)
        for pid in pids:
            try:
                logging.error("KILL TASK {0}".format(pid))
                os.kill(pid, signal.SIGTERM)
            except Exception, e:
                logging.error("deleteTaskLocal : couldn't kill process. error: %s", str(e))
        logging.info("deleteTaskLocal : exiting method")
    
    def is_one_or_more_compute_nodes_running(self, params):# credentials):
        '''
        Checks for the existence of running compute nodes. Only need one running compute node
        to be able to run a job in the cloud.
        '''
        credentials = params["credentials"]
        key_prefix = self.KEY_PREFIX

        if "key_prefix" in params:
            key_prefix = params["key_prefix"]

        try:
            params = {
                "infrastructure": self.INFRA_EC2,
                "credentials": credentials,
                "key_prefix": key_prefix
            }

            all_vms = self.describe_machines(params)
            if all_vms == None:
                return False

            # Just need one running vm
            for vm in all_vms:
                if vm != None and vm['state'] == 'running':
                    return True
            return False

        except:
            return False
    
    def is_queue_head_running(self, params):
        credentials = params["credentials"]
        key_prefix = self.KEY_PREFIX
        if "key_prefix" in params:
            key_prefix = params["key_prefix"]

        try:
            params = {
                "infrastructure": self.INFRA_EC2,
                "credentials": credentials,
                "key_prefix": key_prefix
            }

            all_vms = self.describe_machines(params)
            if all_vms is None:
                return False

            # Just need one running vm with the QUEUEHEAD_KEY_TAG in the name of the keypair
            for vm in all_vms:
                if vm is not None and vm['state'] == 'running' and vm['key_name'].find(self.QUEUE_HEAD_KEY_TAG) != -1:
                    return True

            return False

        except:
            logging.error(sys.exc_info())
            return False
    
    def start_machines(self, params, block=False):
        '''
        This method instantiates ec2 instances
        '''
        logging.info("start_machines : inside method with params : \n%s", pprint.pformat(params))
        try:
            #make sure that any keynames we use are prefixed with stochss so that
            #we can do a terminate all based on keyname prefix
            if "key_prefix" in params:
                key_prefix = params["key_prefix"]
                if not key_prefix.startswith(self.KEY_PREFIX):
                    key_prefix = self.KEY_PREFIX + key_prefix
            else:
                key_prefix = self.KEY_PREFIX

            key_name = params["keyname"]
            if not key_name.startswith(key_prefix):
                params['keyname'] = key_prefix + key_name

            # NOTE: We are forcing blocking mode within the InfrastructureManager class
            # for the launching of VMs because of how GAE joins on all threads before
            # returning a response from a request.
            i = InfrastructureManager(blocking=block)
            res = {}

            # NOTE: We need to make sure that the RabbitMQ server is running if any compute
            # nodes are running as we are using the AMQP broker option for Celery.
            compute_check_params = {
                "credentials": params["credentials"],
                "key_prefix": key_prefix
            }

            if self.is_queue_head_running(compute_check_params):
                #Queue head is running so start as many vms as requested
                res = i.run_instances(params,[])

                self.__copy_celery_config_to_instance(res, params)
                self.__start_celery_via_ssh(res, params)

            else:
                # Need to start the queue head (RabbitMQ)
                params["queue_head"] = True
                vms_requested = int(params["num_vms"])
                requested_key_name = params["keyname"]

                # Only want one queue head, and it must have its own key so
                # it can be differentiated if necessary
                params["num_vms"] = 1
                params["keyname"] = requested_key_name+'-'+self.QUEUE_HEAD_KEY_TAG
                res = i.run_instances(params,[])

                #NOTE: This relies on the InfrastructureManager being run in blocking mode...
                queue_head_ip = res["vm_info"]["public_ips"][0]
                self.__update_celery_config_with_queue_head_ip(queue_head_ip)
                self.__copy_celery_config_to_instance(res, params)

                self.__start_celery_via_ssh(res, params)

                params["keyname"] = requested_key_name
                params["queue_head"] = False

                if vms_requested > 1:
                    #subtract 1 since we can use the queue head as a worker
                    params["num_vms"] = vms_requested - 1
                    res = i.run_instances(params,[])

                    self.__copy_celery_config_to_instance(res, params)
                    self.__start_celery_via_ssh(res, params)

                params["num_vms"] = vms_requested

            logging.info("start_machines : exiting method with result : %s", str(res))
            return res

        except Exception, e:
            traceback.print_exc()
            logging.error("start_machines : exiting method with error : {0}".format(str(e)))
            print "start_machines : exiting method with error :", str(e)
            return None

    def __copy_celery_config_to_instance(self, reservation, params):
        keyfile = os.path.join(os.path.dirname(__file__), '..', "{0}.key".format(params['keyname']))
        logging.debug("keyfile = {0}".format(keyfile))

        if not os.path.exists(keyfile):
            raise Exception("ssh keyfile file not found: {0}".format(keyfile))

        celery_config_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'celeryconfig.py')
        logging.info("celery_config_filename = {0}".format(celery_config_filename))

        if not os.path.exists(celery_config_filename):
            raise Exception("celery config file not found: {0}".format(celery_config_filename))

        for ip in reservation['vm_info']['public_ips']:
            self.__wait_for_ssh_connection(keyfile, ip)
            cmd = "scp -o 'StrictHostKeyChecking no' -i {keyfile} {file} ubuntu@{ip}:celeryconfig.py".format(
                                                                                        keyfile=keyfile,
                                                                                        file=celery_config_filename,
                                                                                        ip=ip)
            logging.info(cmd)
            success = os.system(cmd)

            if success == 0:
                logging.info("scp success: {0} transfered to {1}".format(celery_config_filename, ip))
            else:
                raise Exception("scp failure: {0} not transfered to {1}".format(celery_config_filename, ip))

    def __wait_for_ssh_connection(self, keyfile, ip):
        SSH_RETRY_COUNT = 30
        SSH_RETRY_WAIT = 3

        for _ in range(0, SSH_RETRY_COUNT):
            cmd = "ssh -o 'StrictHostKeyChecking no' -i {0} ubuntu@{1} \"pwd\"".format(keyfile, ip)
            logging.info(cmd)
            success = os.system(cmd)

            if success == 0:
                logging.info("ssh connected to {0}".format(ip))
                return True

            else:
                logging.info("ssh not connected to {0}, sleeping {1}".format(ip, SSH_RETRY_WAIT))
                time.sleep(SSH_RETRY_WAIT)

        raise Exception("Timeout waiting to connect to node via SSH")

    def __start_celery_via_ssh(self, reservation, params):
        logging.info('inside __start_celery_via_ssh, params =\n%s', pprint.pformat(params))
        ##    # Even the queue head gets a celery worker
        ##    # NOTE: We only need to use the -n argument to celery command if we are starting
        ##    #       multiple workers on the same machine. Instead, we are starting one worker
        ##    #       per machine and letting that one worker execute one task per core, using
        ##    #       the configuration in celeryconfig.py to ensure that Celery detects the
        ##    #       number of cores and enforces this desired behavior.
        ##    userstr += "export PYTHONPATH=/home/ubuntu/pyurdme/:/home/ubuntu/stochss/app/\n"
        ##    if self.PARAM_WORKER_QUEUE in parameters:
        ##      start_celery_str = "celery -A tasks worker --autoreload --loglevel=info -Q {0} --workdir /home/ubuntu > /home/ubuntu/celery.log 2>&1 & \n".format(parameters[self.PARAM_WORKER_QUEUE])
        ##    else:
        ##      start_celery_str = "celery -A tasks worker --autoreload --loglevel=info --workdir /home/ubuntu > /home/ubuntu/celery.log 2>&1"
        ##    #userstr+="sudo -u ubuntu screen -d -m bash -c '{0}'\n".format(start_celery_str)  # PyURDME must be run inside a 'screen' terminal as part of the FEniCS code depends on the ability to write to the processe's terminal, screen provides this terminal.
        ##    userstr+="screen -d -m bash -c '{0}'\n".format(start_celery_str)  # PyURDME must be run inside a 'screen' terminal as part of the FEniCS code depends on the ability to write to the process' terminal, screen provides this terminal.

        credentials = params['credentials']

        commands = []
        commands.append('source /home/ubuntu/.bashrc')
        commands.append('export PYTHONPATH=/home/ubuntu/pyurdme/:/home/ubuntu/stochss/app/:/home/ubuntu/stochss/app/backend')
        commands.append('export AWS_ACCESS_KEY_ID={0}'.format(str(credentials['EC2_ACCESS_KEY'])))
        commands.append('export AWS_SECRET_ACCESS_KEY={0}'.format(str(credentials['EC2_SECRET_KEY'])))
        commands.append('celery -A tasks worker --autoreload --loglevel=info --workdir /home/ubuntu > /home/ubuntu/celery.log 2>&1')

        # PyURDME must be run inside a 'screen' terminal as part of the FEniCS code depends on the ability to write to the process' terminal, screen provides this terminal.
        celery_cmd = "sudo screen -d -m bash -c '{0}'\n".format(';'.join(commands))
        # print "reservation={0}".format(reservation)
        # print "params={0}".format(params)

        keyfile = "{0}/../{1}.key".format(os.path.dirname(__file__), params['keyname'])
        logging.info("keyfile = {0}".format(keyfile))

        if not os.path.exists(keyfile):
            raise Exception("ssh keyfile file not found: {0}".format(keyfile))

        for ip in reservation['vm_info']['public_ips']:
            self.__wait_for_ssh_connection(keyfile, ip)

            cmd = "ssh -o 'StrictHostKeyChecking no' -i {0} ubuntu@{1} \"{2}\"".format(keyfile, ip, celery_cmd)
            logging.info(cmd)
            success = os.system(cmd)

            if success == 0:
                logging.info("celery started on {0}".format(ip))
            else:
                raise Exception("Failure to start celery on {0}".format(ip))

    def describe_machines(self, params):
        '''
        This method gets the status of all the instances of ec2
        '''
        # add calls to the infrastructure manager for getting details of
        # machines
        #logging.info("describeMachines : inside method with params : %s", str(params))
        key_prefix = ""
        if "key_prefix" in params:
            key_prefix = params["key_prefix"]
            if not key_prefix.startswith(self.KEY_PREFIX):
                key_prefix = self.KEY_PREFIX + key_prefix
        else:
            key_prefix = self.KEY_PREFIX
        try:
            i = InfrastructureManager()
            res = i.describe_instances(params, [], key_prefix)
            logging.info("describeMachines : exiting method with result : %s", str(res))
            return res

        except Exception, e:
            logging.error("describeMachines : exiting method with error : %s", str(e))
            return None

    def validate_credentials(self, params):
        '''
        This method verifies the validity of ec2 credentials
        '''
        if params['infrastructure'] is None :
            logging.error("validateCredentials: infrastructure param not set")
            return False

        creds = params['credentials']
        if creds is None :
            logging.error("validateCredentials: credentials param not set")
            return False

        if creds['EC2_ACCESS_KEY'] is None :
            logging.error("validateCredentials: credentials EC2_ACCESS_KEY not set")
            return False

        if creds['EC2_SECRET_KEY'] is None :
            logging.error("validateCredentials: credentials EC2_ACCESS_KEY not set")
            return False

        logging.info("validateCredentials: inside method with params : %s", str(params))
        try:
            i = InfrastructureManager()
            logging.info("validateCredentials: exiting with result : %s", str(i))
            return i.validate_Credentials(params)

        except Exception, e:
            logging.error("validateCredentials: exiting with error : %s", str(e))
            return False

    def get_output_results_size(self, aws_access_key, aws_secret_key, output_buckets):
        '''
        This method checks the size of the output results stored in S3 for all of the buckets and keys
         specified in output_buckets.
        @param aws_access_key
         The AWS access key of the user whose output is being examined.
        @param aws_secret_key
         The AWS secret key of the user whose output is being examined.
        @param output_buckets
         A dictionary whose keys are bucket names and whose values are lists of (key name, job name) pairs.
        @return
         A dictionary whose keys are job names and whose values are output sizes of those jobs.
         The output size is either the size specified in bytes or None if no output was found.
        '''
        try:
            logging.info("getSizeOfOutputResults: inside method with output_buckets: {0}".format(output_buckets))
            # Connect to S3
            conn = S3Connection(aws_access_key, aws_secret_key)
            # Output is a dictionary
            result = {}
            for bucket_name in output_buckets:
                # Try to get the bucket
                try:
                    bucket = conn.get_bucket(bucket_name)
                except boto.exception.S3ResponseError:
                    # If the bucket doesn't exist, neither do any of the keys
                    for key_name, job_name in output_buckets[bucket_name]:
                        result[job_name] = None
                else:
                    # Ok the bucket exists, now for the keys
                    for key_name, job_name in output_buckets[bucket_name]:
                        key = bucket.get_key(key_name)
                        if key is None:
                            # No output exists for this key
                            result[job_name] = None
                        else:
                            # Output exists for this key
                            result[job_name] = key.size
            return result

        except Exception, e:
            logging.error("getSizeOfOutputResults: unable to get size with exception: {0}".format(e))
            return None
    
    def fetch_output(self, taskid, outputurl):
        '''
        This method gets the output file from S3 and extracts it to the output 
        directory
        @param taskid: the taskid for which the output has to be fetched
        @return: True : if successful or False : if failed 
        '''
        try : 
            logging.info("fetchOutput: inside method with taskid : {0} and url {1}".format(taskid, outputurl))
            filename = "{0}.tar".format(taskid)
            #the output directory
            #logging.debug("fetchOutput : the name of file to be fetched : {0}".format(filename))
            #baseurl = "https://s3.amazonaws.com/stochkitoutput/output"
            #fileurl = "{0}/{1}".format(baseurl,filename)
            logging.debug("url to be fetched : {0}".format(taskid))
            fetchurlcmdstr = "curl --remote-name {0}".format(outputurl)
            logging.debug("fetchOutput : Fetching file using command : {0}".format(fetchurlcmdstr))
            os.system(fetchurlcmdstr)
            if not os.path.exists(filename):
                logging.error('unable to download file. Returning result as False')
                return False
            return True
        except Exception, e:
            logging.error("fetchOutput : exiting with error : %s", str(e))
            return False

    def terminate_machines(self, params, block=False):
        '''
        This method would terminate all the  instances associated with the account
        that have a keyname prefixed with stochss (all instances created by the backend service)
        params must contain credentials key/value
        '''
        key_prefix = self.KEY_PREFIX
        if "key_prefix" in params and not params["key_prefix"].startswith(key_prefix):
            key_prefix += params["key_prefix"]
        elif "key_prefix" in params:
            key_prefix = params["key_prefix"]

        try:
            logging.info("Terminating compute nodes with key_prefix: {0}".format(key_prefix))
            i = InfrastructureManager(blocking=block)
            res = i.terminate_instances(params,key_prefix)
            return True

        except Exception, e:
            logging.error("Terminate machine failed with error : %s", str(e))
            return False

    def __update_celery_config_with_queue_head_ip(self, queue_head_ip):
        # Write queue_head_ip to file on the appropriate line
        current_dir = os.path.dirname(os.path.abspath(__file__))
        celery_config_filename = os.path.join(current_dir, "celeryconfig.py")
        celery_template_filename = os.path.join(current_dir, "conf", "celeryconfig.py.template")

        logging.debug("celery_config_filename = {0}".format(celery_config_filename))
        logging.debug("celery_template_filename = {0}".format(celery_template_filename))

        celery_config_lines = []
        with open(celery_template_filename) as celery_config_file:
            celery_config_lines = celery_config_file.readlines()

        with open(celery_config_filename, 'w') as celery_config_file:
            for line in celery_config_lines:
                if line.strip().startswith('BROKER_URL'):
                    celery_config_file.write('BROKER_URL = "amqp://stochss:ucsb@{0}:5672/"\n'.format(queue_head_ip))
                else:
                    celery_config_file.write(line)

        # Now update the actual Celery app....
        #TODO: Doesnt seem to work in GAE until next request comes in to server
        my_celery = CelerySingleton()
        my_celery.configure()










################## tests #############################
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m' #yellow
    FAIL = '\033[91m'
    ENDC = '\033[0m'

##########################################
##########################################
# def test_stochoptim(backend, compute_check_params):
#     '''
#     This tests a stochoptim job using a local run and a cloud run
#     '''
#     started_queue_head = False
#     queue_key = None
#     keypair_name = backend.KEYPREFIX+"-ch-stochoptim-testing"
#     if backend.is_queue_head_running(compute_check_params):
#         print "Assuming you already have a queue head up and running..."
#
#     else:
#         started_queue_head = True
#         print "Launching queue head / master worker..."
#         launch_params = {
#             "infrastructure": backend.INFRA_EC2,
#             "credentials": credentials,
#             "num_vms": 1,
#             "group": keypair_name,
#             "image_id": backend.WORKER_AMIS[backend.INFRA_EC2],
#             "instance_type": 't1.micro',#"c3.large",
#             "key_prefix": keypair_name,
#             "keyname": keypair_name,
#             "use_spot_instances": False
#         }
#
#         launch_result = backend.start_machines(launch_params, block=True)
#         if not launch_result["success"]:
#             print "Failed to start master machine..."
#             sys.exit(1)
#
#         print "Done. Sleeping 2 mins while machines initialize (status checks)"
#         time.sleep(120)
#
#     # We need to start our own workers first.
#     cores_to_use = 4
#     print "Launching {0} slave worker(s)...".format(cores_to_use)
#     launch_params = {
#         "infrastructure": backend.INFRA_EC2,
#         "credentials": credentials,
#         "num_vms": cores_to_use,
#         "group": keypair_name,
#         "image_id": backend.WORKER_AMIS[backend.INFRA_EC2],
#         "instance_type": 't1.micro',#"c3.large",
#         "key_prefix": keypair_name,
#         "keyname": keypair_name,
#         "use_spot_instances": False
#     }
#
#     # Slaves dont need to be started in blocking mode, although
#     # blocking mode is being forced inside the InfrastructureManager
#     # currently.
#     #comment this block out if you already have 4 workers started
#     #from a previous test
#     #cjklaunch_result = backend.startMachines(launch_params, block=False)
#     #cjkif not launch_result["success"]:
#         #cjkprint "Failed to start slave worker(s)..."
#         #cjksys.exit(1)
#     #cjkprint "Done2. Sleeping 2 mins while machines initialize (status checks)"
#     #cjktime.sleep(120)
#
#     print 'all nodes needed have been launched'
#     sys.stdout.flush()
#
#     # Then we can execute the task.
#     file_dir_path = os.path.dirname(os.path.abspath(__file__))
#     path_to_model_file = os.path.join(file_dir_path, "../../stochoptim/inst/extdata/birth_death_REMAImodel.R")
#     path_to_model_data_file = os.path.join(file_dir_path, "../../stochoptim/inst/extdata/birth_death_REdata0.txt")
#     path_to_final_data_file = os.path.join(file_dir_path, "../../stochoptim/inst/extdata/birth_death_REdata.txt")
#     params = {
#         'credentials':{'EC2_ACCESS_KEY':access_key, 'EC2_SECRET_KEY':secret_key},
#         "key_prefix": keypair_name,
#         "job_type": "mcem2",
#         "cores": cores_to_use,
#         "model_file": open(path_to_model_file, 'r').read(),
#         "model_data": {
#             "extension": "txt",
#             "content": open(path_to_model_data_file, 'r').read()
#         },
#         "final_data": {
#             "extension": "txt",
#             "content": open(path_to_final_data_file, 'r').read()
#         },
#         "bucketname": "cjktestingstochoptim",
#         "paramstring": "exec/cedwssa.r --K.ce 1e5 --K.prob 1e6"
#     }
#
#     print "\nCalling execute_task now..."
#     sys.stdout.flush()
#     result = backend.execute_task(params)
#
#     if result["success"]:
#         print "Succeeded..."
#         celery_id = result["celery_pid"]
#         queue_name = result["queue"]
#
#         # call the poll task process
#         poll_task_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poll_task.py")
#         os.system("python {0} {1} {2} > poll_task_{1}.log 2>&1".format(poll_task_path, celery_id, queue_name))
#         task_id = result["db_id"]
#
#         describe_task_params = {
#             "AWS_ACCESS_KEY_ID": access_key,
#             "AWS_SECRET_ACCESS_KEY": secret_key,
#             "taskids": [task_id]
#         }
#
#         print "\nCalling describe_task..."
#         desc_result = backend.describe_task(describe_task_params)[task_id]
#
#         while desc_result["status"] != "finished":
#             if "output" in desc_result:
#                 print "[{0}] [{1}] [{2}] [{3}]".format(
#                     desc_result["taskid"],
#                     desc_result["status"],
#                     desc_result["message"],
#                     desc_result["output"]
#                 )
#             elif "message" in desc_result:
#                 print "[{0}] [{1}] [{2}]".format(
#                     desc_result["taskid"],
#                     desc_result["status"],
#                     desc_result["message"]
#                 )
#             else:
#                 print "[{0}] [{1}]".format(
#                     desc_result["taskid"],
#                     desc_result["status"]
#                 )
#
#             time.sleep(60)
#             print "\nCalling describeTask..."
#             desc_result = backend.describe_task(describe_task_params)[task_id]
#
#         print "Finished..."
#         print desc_result["output"]
#         terminate_params = {
#             "infrastructure": backend.INFRA_EC2,
#             "credentials": credentials,
#             "key_prefix": keypair_name
#         }
#
#         print "\nStopping all VMs..."
#
#         if backend.terminate_machines(terminate_params):
#             print "Stopped all machines!"
#         else:
#             print "Failed to stop machines..."
#
#     else:
#         print "Failed..."
#         if "exception" in result:
#             print result["exception"]
#             print result["traceback"]
#         else:
#             print result["reason"]

##########################################
##########################################

def test_stochss_local():
    os.chdir(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../..'))
    print "pwd = ", os.path.abspath(os.curdir)

    backend = backendservices()

    with open('examples/dimer_decay.xml', 'r') as xmlfile:
        model_xml_doc = xmlfile.read()

    print 'testing local task execution...'
    task_args = {}
    pids = []

    NUMTASKS = 2
    for pid in range(NUMTASKS):
        task_args['paramstring'] = './StochKit/ssa -t 100 -i 10 -r 10 --keep-trajectories --seed 706370 --label'
        task_args['document'] = model_xml_doc
        task_args['job_type'] = 'stochkit'      # stochkit (ssa) or stochkit-ode (ode) or and mcem2

        res = backend.execute_local_task(task_args)
        if res is not None:
            print 'task {0} local results: {1}'.format(str(pid), str(res))
            pids.append(res['pid'])
            print
            print 'number of pids: {0}, pids = {1}'.format(str(len(pids)), str(pids))

        res = backend.check_local_task_status(pids)
        if res is not None:
            print 'status: {0}'.format(str(res))
        time.sleep(5)

    time.sleep(5)  # need to sleep here to allow for process spawn
    print 'deleting pids: {0}'.format(str(pids))
    backend.delete_local_task(pids)

def test_stochss_cloud(start_vms, key_name, security_group):
    os.chdir(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../..'))
    print "pwd = ", os.path.abspath(os.curdir)

    backend = backendservices()

    try:
       access_key = os.environ["AWS_ACCESS_KEY"]
       secret_key = os.environ["AWS_SECRET_KEY"]
    except KeyError:
       print "main: Environment variables AWS_ACCESS_KEY and AWS_SECRET_KEY not set, cannot continue"
       sys.exit(1)

    if not os.environ.has_key("AWS_ACCESS_KEY_ID"):
        os.environ["AWS_ACCESS_KEY_ID"] = access_key
    if not os.environ.has_key("AWS_SECRET_ACCESS_KEY"):
        os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key

    credentials = {'EC2_ACCESS_KEY': access_key,
                   'EC2_SECRET_KEY': secret_key}

    compute_check_params = {"infrastructure": backend.INFRA_EC2,
                            "credentials": credentials,
                            "key_prefix": 'stochss-test-1-queuehead'}

    if backend.validate_credentials(compute_check_params):
        print bcolors.OKGREEN + 'valid creds = True' + bcolors.ENDC
    else:
        print bcolors.FAIL + 'valid creds = False' + bcolors.ENDC
        return

    dynamodb.create_table(backendservices.TABLE_NAME)

    # #### run this part to test stochoptim (parameter estimation code) #####
    # NOTE: Uncomment this to test stochkit2 job run
    params = {}
    params['credentials'] = credentials
    params['infrastructure'] = backend.INFRA_EC2
    params['num_vms'] = 1
    params['group'] = 'stochss-test-1-queuehead'

    # this is used for workers.  its overridden for head node in
    # agents/ec2_agent.py to be c3.large b/c we need more resources there
    # head node is also used as a worker node
    params['instance_type'] = 'c3.large'

    # stochss will prefix whatever keyname you give here: stochss, queuehead tag for queueheads
    params['keyname'] = 'stochss-test-1-queuehead'
    params['use_spot_instances'] = False

    if params['infrastructure'] == backendservices.INFRA_EC2 :
        params['image_id'] = backend.WORKER_AMIS[backend.INFRA_EC2]
    else :
        raise TypeError("Error, unexpected infrastructure type: "+params['infrastructure'])

    print 'start_vms = ', start_vms
    if start_vms:
        res = backend.start_machines(params)

        if res is None or not res['success'] :
            raise TypeError("Error, start_machines failed!")

        print bcolors.OKGREEN + 'start_machines succeeded ' + str(res) +  bcolors.ENDC
        print 'started VMs, sleeping for a couple minutes to allow for initialization'

        # for aws status checks
        time.sleep(120)

    if backend.is_queue_head_running(compute_check_params):
        print bcolors.OKGREEN + 'Queue Head running = True' + bcolors.ENDC
    else:
        print bcolors.FAIL + 'Queue Head running = False' + bcolors.ENDC
        return

    print 'describe_machines:', backend.describe_machines(params)

    with open('examples/dimer_decay.xml', 'r') as xmlfile:
        model_xml_doc = xmlfile.read()

    print '\ntesting cloud task execution...'

    taskargs = {}
    pids = []

    taskargs['AWS_ACCESS_KEY_ID'] = credentials['EC2_ACCESS_KEY']
    taskargs['AWS_SECRET_ACCESS_KEY'] = credentials['EC2_SECRET_KEY']

    NUMTASKS = 2
    for pid in range(NUMTASKS):
        taskargs['paramstring'] = 'ssa -t 100 -i 100 -r 100 --keep-trajectories --seed 706370 --label'
        taskargs['document'] = model_xml_doc

        # make this unique across all names/users in S3!
        # bug in stochss: if the bucketname is aleady in s3,
        # tasks run but never update their results in s3 (silent failur)
        # taskargs['bucketname'] = 'stochsstestbucket2'

        # options for job_type are stochkit (ssa), stochkit-ode (ode),
        # and mcem2 (for paramsweep/stochoptim)
        taskargs['job_type'] = 'stochkit'

        # sometimes it takes awhile for machine to be ready
        # if this fails with connection refused
        # and you just started a VM recently, then leave the VM up and
        # retry (comment out startMachine above)
        cloud_result = backend.execute_task(taskargs)

        print bcolors.OKGREEN + 'cloud_result on executeTask: ' + str(cloud_result) + bcolors.ENDC
        if not cloud_result['success']:
            print bcolors.FAIL + 'executeTask failed!' + bcolors.ENDC
            sys.exit(1)

        res = cloud_result['celery_pid']
        taskid = cloud_result['db_id']
        pids.append(taskid)

    #check each task's status
    taskargs['taskids'] = pids
    done = {}
    count = NUMTASKS

    while len(done) < count:
        for pid in pids:
            task_status = backend.describe_task(taskargs)
            job_status = task_status[pid]  #may be None

            if job_status is not None:
                print 'task id {0} status: {1}'.format(str(pid), job_status['status'])

                if job_status['status'] == 'finished':
                    print 'cloud job {0} is finished, output: '.format(str(pid))
                    print job_status['output']
                    done[pid] = True

                    #don't kill off tasks, wait for them to finish
                    #this code hasn't been tested in awhile
                    #elif job_status['status'] == 'active':
                    #print '\tDELETING task {0}'.format(str(i))
                    #count = count - 1
                    #backend.deleteTasks([i])

            else:
                print 'task id {0} status is None'.format(str(pid))

        print '{0} jobs have finished!\n'.format(len(done))

    ############################
    # this terminates instances associated with this users creds and KEYPREFIX keyname prefix
    print 'terminate_machines outputs to the testoutput.log file'
    # print 'terminate_machines is commented out -- be sure to terminate your instances or uncomment!'
    if backend.terminate_machines(params):
        print 'Terminated all machines!'
    else:
        print 'Failed to terminate machines...'
    backend.describe_machines(params)


##########################################
##########################################

if __name__ == "__main__":
    '''
    Note that these must be set for this function to work properly:
    export STOCHSS_HOME=/path/to/stochss/git/dir/stochss
    export PYTHONPATH=${STOCHSS_HOME}:.:..
    export PATH=${PATH}:${STOCHSS_HOME}/StochKit
    '''

    # logging.basicConfig(filename='testoutput.log', filemode='w', level=logging.DEBUG)
    logging.basicConfig(level=logging.DEBUG)

    # # test_stochss_local()
    #
    # start_vms = False
    # key_name = 'stochss-test-1-queuehead'
    # security_group = 'stochss-test-1-queuehead'
    # test_stochss_cloud(start_vms=start_vms, key_name=key_name, security_group=security_group)

    # print 'Running StochOptim Tests'
    # sys.stdout.flush()
    # #I haven't gotten this to work for me yet, but have run out of time
    # #trying to investigate.  Pushing this to Mengyuan's task list - Chandra 7/23/14
    # test_stochoptim(backend,compute_check_params)


