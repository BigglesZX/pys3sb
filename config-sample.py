'''
pys3sb config file

Specifies the application configuration including AWS credentials and backup tasks.
'''


''' Your AWS access key (20 chars) '''
AWS_KEY = 'ABC123ABC123ABC123AB'
''' Your AWS secret key (40 chars) '''
AWS_SECRET_KEY = 'ABC123ABC123ABC123ABABC123ABC123ABC123AB'


''' S3 bucket name where backups will be uploaded '''
S3_BUCKET = 's3sb'


'''
Backup task definitions

name: internal name for the backup task, used when creating files (required)
friendly_name: used in messaging to refer to task (required)
frequency: 'daily' for daily backup, 'weekly' for weekly backup or 'monthly' for monthly (required)
s3_directory_name: name used to create directory on s3 bucket for this task (required)

database: this section can be omitted to skip database backup
    hostname: hostname for the site's database, or localhost, or 127.0.0.1
    username: MySQL user used in database connection
    password: password for above MySQL user
    name: name of database to back up

files: this section can be omitted to skip file backup
    path: path of site to back up, absolute or relative to current working directory
    exclude: list of paths to exclude from backup, absolute or relative to current working directory
    
Note that for each task, at least one of the "files" and "database" sections must be specified.

'''
TASKS = [
    {
        'name': 'mysite',
        'friendly_name': 'backup of mysite files and database',
        'frequency': 'daily',
        's3_directory_name': 'mysite',
        'database': {
            'hostname': 'db.mysite.com',
            'username': 'myuser',
            'password': 'mypass',
            'name': 'mysite',
        },
        'files': {
            'path': '/var/www/mysite',
            'exclude': ['/var/www/mysite/cache'],
        },
    },
]