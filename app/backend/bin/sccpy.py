import sys
import boto
import boto.s3
from boto.s3.lifecycle import Lifecycle, Expiration

class AmazonS3Agent():
    def upload_file(self, file, bucket_name):
        try:
            lifecycle = Lifecycle()
            lifecycle.add_rule('rulename', prefix='logs/', status='Enabled', expiration=Expiration(days=10))
            conn = boto.connect_s3()

            if conn.lookup(bucket_name): #bucketexisits
                bucket = conn.get_bucket(bucket_name)
            else:
                #create a bucket
                bucket = conn.create_bucket(bucket_name, location=boto.s3.connection.Location.DEFAULT)

            bucket.configure_lifecycle(lifecycle)

            from boto.s3.key import Key
            k = Key(bucket)
            k.key = file
            k.set_contents_from_filename(file, cb=self.percent_cb, num_cb=10)
            k.set_acl('public-read-write')

        except Exception,e:
            sys.stdout.write("S3Agent failed with exception:\n{0}".format(str(e)))
            sys.stdout.flush()
            raise e


    def percent_cb(self,complete, total):
        sys.stdout.write('.')
        sys.stdout.flush()

if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise Exception("Invalid params passed to {0}!".format(sys.argv[0]))

    file = sys.argv[1]
    bucket_name = sys.argv[2]
    agent = AmazonS3Agent()
    agent.upload_file(file, bucket_name)