import boto

"""
All DynamoBD related methods
"""

def describe_task(task_ids, table_name):
    res = {}
    try:
        print 'inside describe_task method with task_ids = {0} and table_name {1}'.format(str(task_ids), table_name)
        dynamodb = boto.connect_dynamodb()
        if not table_exists(dynamodb, table_name):   return res
        table = dynamodb.get_table(table_name)

        for task_id in task_ids:
            try:
                item = table.get_item(hash_key=task_id)
                res[task_id] = item
            except Exception,e:
                res[task_id] = None
        return res
    except Exception,e:
        print "exiting describe_task with error : {0}".format(str(e))
        print str(e)
        return res

def remove_task(table_name, task_id):
    print 'inside remove_task method with table_name = {0} and task_id = {1}'.format(table_name, task_id)
    try:
        dynamodb = boto.connect_dynamodb()

        if table_exists(dynamodb, table_name):
            table = dynamodb.get_table(table_name)
            item = table.get_item(hash_key=task_id)
            item.delete()
            return True

        else:
            print 'exiting remove_task with error : table doesn\'t exists'
            return False

    except Exception,e:
        print 'exiting remove_task with error {0}'.format(str(e))
        return False

def create_table(table_name=str()):
    print 'inside create_table method with tablename :: {0}'.format(table_name)

    if table_name == None:
        table_name = "stochss"
        print 'default table name picked as stochss'

    try:
        print 'connecting to dynamodb'
        dynamo=boto.connect_dynamodb()

        #check if table already exists
        print 'checking if table {0} exists'.format(table_name)
        if not table_exists(dynamo,table_name):
            print 'creating table schema'
            myschema = dynamo.create_schema(hash_key_name='taskid',
                                            hash_key_proto_value=str)
            table = dynamo.create_table(name=table_name,
                                        schema=myschema,
                                        read_units=6,
                                        write_units=4)
        else:
            print "table already exists"

        return True

    except Exception,e:
        print str(e)
        return False

def table_exists(dynamodb, table_name):
    try:
        table = dynamodb.get_table(table_name)
        if table is None:
            print "table doesn't exist"
            return False
        else:
            return True

    except Exception,e:
        print str(e)
        return False

def update_entry(task_id=str(), data=dict(), table_name=str()):
    '''
     check if entry exists
     create a entry if not or
     update the status
    '''
    try:
        print 'inside update_entry method with taskid = {0} and data = {1}'.format(task_id, str(data))
        dynamodb = boto.connect_dynamodb()
        if not table_exists(dynamodb, table_name):
            print "invalid table name specified"
            return False

        table = dynamodb.get_table(table_name)
        item = table.new_item(hash_key=str(task_id), attrs=data)
        item.put()
        return True

    except Exception,e:
        print 'exiting update_entry with error : {0}'.format(str(e))
        return False