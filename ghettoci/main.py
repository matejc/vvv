#! /usr/bin/python3
"""

Continuous integration server, ghetto style

What it is
--------------

Python script in few hundred lines fullfilling your dirty little continuos integration needs.

What it does
--------------

1. Runs update on a source folder on a Subversion repository (note: VCS backend easy to change)

2. See if there are new commits since the last run

3. Run tests if the source code in fact was changed

4. See if the tests status has changed from success to failure or vice versa

5. Print results to stdout, send email notifications to the team

Why to use
---------------

To improve your software project quality and cost effectiveness, 
you want to automatically detect bad commits breaking your project 
`without need to install 48 MB of Java software <http://jenkins-ci.org/>`_.
This script is mostly self-contained, easy to understand, easy to hack into pieces and customize for your very own need.

How to use
--------------

Create Python 3 virtualenv and run ghetto script using Python interpreter configured under this virtualenv::

    # We install directly under our UNIX user home folder
    cd ~
    virtualenv -p python3.2 ghetto
    source ghetto/bin/activate
    pip install plac

    # Install ghetto-ci.py command by downloading it from Github using wget
    wget --no-check-certificate -O ghetto-ci.py xxx

    # Running the script, using the Python environment prepared above
    ghetto/bin/python ghettoci.py

Now you need have

* A software repository folder. This must be pre-checked out Subversion repository where
  you can run ``svn up`` command.

* A command to execute unit tests and such. Must return process exit code 0 on success.

* A location where you store the status file. Status file keeps track whether the last round
  or tests succeeded or failed. You'll get email reports only when the test status changed -
  there is little need to get "tests succeeded" email for every commit. 

* Email server details to send out notifications. Gmail works perfectly.

Example of a command::

    # Will print output to console because email notification details are not given
    ghetto/bin/python ghettoci.py 
    
Then just make *ghettoci* to poll the repository in UNIX crom (Ubuntu example).
Create file ``/etc/cron.hourly/ghetto-ci``::


... or just use OSX or Windows task automators.

Credits and source
--------------------

`Ghetto CI lives on Github, in VVV project <https://github.com/miohtama/vvv>`_.

Mikko Ohtamaa, the original author (`blog <http://opensourcehacker.com>`_, `Twitter <http://twitter.com/moo9000>`_)

Licensed under `WTFPL <http://sam.zoy.org/wtfpl/COPYING>`_.

`Ghetto style explained <http://www.urbandictionary.com/define.php?term=ghetto+style>`_.

"""

# pylint complains about abstract Python 3 members and ABCMeta, this will be fixed in the future
# pylint: disable=R0201, W0611

# Python imports
from abc import ABCMeta, abstractmethod
from email.mime.text import MIMEText 
import pickle
import sys
import subprocess
from smtplib import SMTP_SSL, SMTP 

def shell(cmdline):
    """
    Execute a shell command.

    :returns: (exitcode, stdout / stderr output as string) tuple
    """

    process = subprocess.Popen(cmdline, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

    # XXX: Support stderr interleaving
    out, err = process.communicate()

    # :E1103: *%s %r has no %r member (but some types could not be inferred)*
    # pylint: disable=E1103 
    out = out.decode("utf-8")
    err = err.decode("utf-8")

    return (process.returncode, out + err)    

class Status:
    """
    Store CI status of a test run.

    Use Python pickling serialization for making status info persistent.
    """

    def __init__(self):
        self.test_success = False
        self.last_commit_id = None

    @classmethod
    def read(cls, path):
        """
        Read status file.

        Return fresh status if file does not exist.
        """    
        try:
            f = open(path, "rb")
        except OSError:
            # Status file do not exist, get default status
            return Status()

        try:
            content = f.read()
            return pickle.loads(content)
        finally:
            f.close()
        
    @classmethod
    def write(cls, path, status):
        """
        Write status file
        """        
        f = open(path, "wt")
        content = pickle.dumps(status)
        f.write(content)
        f.close()


class Repo(metaclass=ABCMeta):
    """ 
    Define interface for presenting one monitored software repository in ghetto-ci.
    """
    def __init__(self, path):
        """
        :param path: Abs FS path to monitored repository
        """
        self.path = path

    @abstractmethod
    def update(self):
        """ Update repo from version control """
        pass

    @abstractmethod
    def get_last_commit_info(self):
        """
        Get the last commit status.

        :return tuple(commit id, commiter, message, raw_output) or (None, None, None, raw_output) on error
        """
        return (None, None, None)

class SVNRepo(Repo):
    """ Handle Subversion repository update and last commit info extraction """

    def update(self):
        """
        Run repo update in a source folder
        """
        exitcode, output = shell("svn up %s" % self.path)
        return exitcode == 0, output

    def get_last_commit_info(self):
        """
        Get the last commit status.
        """
        info, output = self.get_svn_info()
        if not info:
            return (None, None, None, output)

        return info["Revision"]

    def get_svn_info(self):
        """
        Get svn info output parsed to dict
        """
        exit_code, output = shell("svn info %s" % self.path)
        if exit_code != 0:
            return None, output

        data = {}
        for line in output.split("\n"):
            key, values = line.split(":")
            value = ",".join(values)
            data[key] = value

        return data, output

class Notifier:
    """
    Intelligent spam being. Print messages to stdout and send emai if 
    SMTP server details are available.
    """

    def __init__(self, server, port, username, password, receivers, from_address):
        """
        :param server: SMTP server
        
        :param port: SMTP port, autodetects SSL
        
        :param username: SMTP credentials 
        
        :param password: SMTP password
        
        :param receivers: String, comma separated list of receivers

        :param from_email: Sender's email address 
        """

        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.receivers = receivers
        self.from_address = from_address

        # This would be nice trick, but let's keep linter happy
        # self.__dict__.update(kwargs)

    def send_email_notification(self, subject, output):
        """

        Further info:

        * http://docs.python.org/py3k/library/email-examples.html

        :param receivers: list of email addresses

        :param subject: Email subject

        :param output: Email payload
        """
    
        if self.port == 465:
            # SSL encryption from the start
            smtp = SMTP_SSL(self.server, self.port)
        else: 
            # Plain-text SMTP, or opt-in to SSL using starttls() command 
            smtp = SMTP(self.server, self.port)

        msg = MIMEText(output, "text/plain")
        msg['Subject'] = subject
        msg['From'] = self.from_address

        # SMTP never works on the first attempt...
        smtp.set_debuglevel(True)

        # SMTP authentication is optional
        if self.username and self.password:
            smtp.login(self.username, self.password)

        try:
            smtp.sendmail(self.from_address, self.receivers, msg.as_string())
        finally:
            smtp.close()

    def print_notification(self, subject, output):
        """
        Dump the notification to stdout
        """
        print(subject)
        print("-" * len(subject))
        print(output) 

    def notify(self, subject, output):
        """
        Notify about the tests status.
        """
        if self.server:
            self.send_email_notification(subject, output)

        self.print_notification(subject, output)
        
def run_tests(test_command):
    """
    Run testing command.

    Assume exit code = 0 -> test success
    """
    exitcode, output = shell(test_command)
    return (exitcode == 0, output)


# Parsing command line with plac rocks
# http://plac.googlecode.com/hg/doc/plac.html
def main(smtpserver : ("SMTP server address for mail out", "option"), 
         smtpport : ("SMTP server port for mail out", "option", None, int), 
         smtpuser : ("SMTP server username", "option"),
         smtppassword : ("SMTP server password", "option"),
         smtpfrom : ("From email address"),
         receivers : ("Email receives as comma separated string", "option"),
         force : ("Run tests regardless if there have been any repository updates", "flag"),

         repository : ("Monitored source control repository (SVN)", "positional"), 
         statusfile : ("Status file to hold CI history of tests", "positional"),
         testcommand : ("Command to run tests. Exit code 0 indicates test success", "positional"), 
         ):
    """
    ghetto-ci

    A simple continous integration server.
    
    ghetto-ci will monitor the software repository.
    Give a (Subversion) software repository and a test command run test against it.
    Make this command run regularly e.g. using UNIX cron service.    
    You will get email notification when test command status changes from exit code 0.

    For more information see https://github.com/miohtama/vvv
    """


    notifier = Notifier(server=smtpserver, port=smtpport, 
                      user=smtpuser, password=smtppassword, from_address=smtpfrom,
                      receivers=receivers)

    repo = SVNRepo(repository)    
    status = Status.read(statusfile)

    success, output = repo.update()

    # Handle repo update failure
    if not success:
        notifier.notify("Could not update repository: %s. Probably not valid SVN repo?\n" % repository, output)
        return 1

    commit_id, commit_author, commit_message, output = repo.get_last_commit_info()

    # Handle repo info failure
    if not commit_id:
        notifier.notify("Could not get commit info: %s\n%s" % (repository, output), "Check svn info by hand")
        return 1

    # See if repository status has changed
    if commit_id  != status.last_commit_id or force:
        test_success, output = run_tests(testcommand)
    else:
        # No new commits, nothing to do
        return 0

    # Decorate test run output with commit info as the header
    output = "Last commit %s: %s by %s\n %s" % (commit_id, commit_message, commit_author, output)    
    
    # Test run status have changed since last run
    if test_success != status.test_success:

        if test_success:
            subject = "Test now succeed @ %s" % repository
        else:
            subject = "Test now fail @ %s" % repository

        notifier.notify(subject, output)

    # Update persistent test status 
    new_status = Status()
    new_status.last_commit_id = commit_id
    new_status.test_success = test_success
    Status.write(statusfile, new_status)

    if test_success:
        return 0
    else:
        return 1

def entry_point():
    """
    Enter the via setup.py entry_point declaration.

    Handle UNIX style application exit values
    """
    import plac
    exitcode = plac.call(main)
    sys.exit(exitcode)

if __name__ == "__main__":
    entry_point()