import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../lib/boto'))

from time import sleep

import tasks
from celery.result import AsyncResult

def get_workers_consuming_from_queue(from_queue):
    '''
    Returns a list of the names of all workers that are consuming from the
    from_queue, or an empty list if no workers are consuming from the queue.
    '''
    worker_names = []
    app = tasks.CelerySingleton().app

    all_worker_assignments = app.control.inspect().active_queues()

    for worker_name in all_worker_assignments:
        worker_queues = all_worker_assignments[worker_name]
        for queue in worker_queues:
            if queue["name"] == from_queue:
                worker_names.append(worker_name)

    return worker_names

def poll_task(task_id, queue_name):
    # Get the task
    result = AsyncResult(task_id)

    # Wait until its ready, checking once/minute
    while not result.ready():
        print "Task {0} still not done...".format(task_id)
        sleep(60)

    print "Task {0} done.".format(task_id)

    # Ok its done, need to get the workers now
    worker_names = tasks.get_workers_consuming_from_queue(queue_name)

    if worker_names:
        print "Rerouting workers {0} from {1} back to main queue".format(worker_names, queue_name)
        # If there are still workers consuming from this queue (i.e.
        # they haven't been terminated by the alarms yet), we need
        # to reclaim them.
        tasks.reroute_workers(worker_names, "celery", from_queue=queue_name)

    return True

def print_usage_and_exit(exe_name):
    print "Error in command line arguments!"
    print "Expected Usage: {0} [task_id] [queue_name]".format(exe_name)
    sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 2:
        task_id = sys.argv[1]
        queue_name = sys.argv[2]
        poll_task(task_id, queue_name)

    else:
        print_usage_and_exit(sys.argv[0])
