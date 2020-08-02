#!/usr/bin/env python
#$Rev: 1300 $
#$LastChangedDate: 2007-02-28 13:46:16 -0800 (Wed, 28 Feb 2007) $

import os
import subprocess
import random
import sys
import signal
import socket
import telnetlib
import time
import threading
import urlparse

from time import sleep

# Ensure booleans exist (not needed for Python 2.2.1 or higher)
try:
    True
except NameError:
    False = 0
    True = not False

class ThreadPool:

    """Flexible thread pool class.  Creates a pool of threads, then
    accepts tasks that will be dispatched to the next available
    thread."""
    
    def __init__(self, numThreads):

        """Initialize the thread pool with numThreads workers."""
        
        self.__threads = []
        self.__resizeLock = threading.Condition(threading.Lock())
        self.__taskLock = threading.Condition(threading.Lock())
        self.__tasks = []
        self.__processed = 0;
        self.__isJoining = False
        self.setThreadCount(numThreads)

    def setThreadCount(self, newNumThreads):

        """ External method to set the current pool size.  Acquires
        the resizing lock, then calls the internal version to do real
        work."""
        
        # Can't change the thread count if we're shutting down the pool!
        if self.__isJoining:
            return False;
        
        self.__resizeLock.acquire()
        try:
            self.__setThreadCountNolock(newNumThreads)
        finally:
            self.__resizeLock.release()
            return True;

    def __setThreadCountNolock(self, newNumThreads):
        
        """Set the current pool size, spawning or terminating threads
        if necessary.  Internal use only; assumes the resizing lock is
        held."""
        
        # If we need to grow the pool, do so
        while newNumThreads > len(self.__threads):
            newThread = ThreadPoolThread(self)
            self.__threads.append(newThread)
            newThread.start()
        # If we need to shrink the pool, do so
        while newNumThreads < len(self.__threads):
            self.__threads[0].goAway()
            del self.__threads[0]

    def getThreadCount(self):

        """Return the number of threads in the pool."""
        
        self.__resizeLock.acquire()
        try:
            return len(self.__threads)
        finally:
            self.__resizeLock.release()

    def queueTask(self, task, args=None, taskCallback=None):

        """Insert a task into the queue.  task must be callable;
        args and taskCallback can be None."""
        
        if self.__isJoining == True:
            return False
        if not callable(task):
            return False
        
        self.__taskLock.acquire()
        try:
            self.__tasks.append((task, args, taskCallback))
            return True
        finally:
            self.__taskLock.release()

    def getNextTask(self):

        """ Retrieve the next task from the task queue.  For use
        only by ThreadPoolThread objects contained in the pool."""
        
        self.__taskLock.acquire()
        try:
            if self.__tasks == []:
                return (None, None, None)
            else:
                self.__processed = self.__processed + 1;
                task = self.__tasks.pop(0);
                return task;
        finally:
            self.__taskLock.release()
    
    def joinAll(self, waitForTasks = True, waitForThreads = True):

        """ Clear the task queue and terminate all pooled threads,
        optionally allowing the tasks and threads to finish."""
        
        # Mark the pool as joining to prevent any more task queueing
        self.__isJoining = True

        # Wait for tasks to finish
        if waitForTasks:
            while self.__tasks != []:
                sleep (0.1)

        # Tell all the threads to quit
        self.__resizeLock.acquire()
        try:
            # Wait until all threads have exited
            if waitForThreads:
                for t in self.__threads:
                    t.goAway()
                for t in self.__threads:
                    t.join()
                    del t
            self.__setThreadCountNolock(0)
            self.__isJoining = True

            # Reset the pool for potential reuse
            self.__isJoining = False
        finally:
            self.__resizeLock.release()


        
class ThreadPoolThread (threading.Thread):

    """ Pooled thread class. """
    
    threadSleepTime = 0.1;

    def __init__(self, pool):

        """ Initialize the thread and remember the pool. """
        
        threading.Thread.__init__(self)
        self.__pool = pool
        self.__isDying = False
        
    def run(self):
    
        """ Until told to quit, retrieve the next task and execute
        it, calling the callback if any.  """
        
        while self.__isDying == False:
            cmd, args, callback = self.__pool.getNextTask()
            # If there's nothing to do, just sleep a bit
            if cmd is None:
                sleep (ThreadPoolThread.threadSleepTime)
            elif callback is None:
                cmd(args)
            else:
                callback(cmd(args))
                
    def goAway(self):

        """ Exit the run loop next time through."""
        
        self.__isDying = True


# pub_urls - The list of URLs to compare between the proxy
# and a direct connection.
#
# You can create additional automated tests for your proxy by
# adding URLs to this array.  This will have no effect on your
# grade, but may be helpful in testing and debugging your proxy.
#
# When you are testing against real web servers on the Internet, 
# you may see minor differences between the proxy-fetched page and
# the regular page- possibly due to load balancing or dynamically
# generated content.  If there is only a single line that doesn't
# match between the two, it is likely a product of this sort of
# variation.
#
# Note that since this test script compares transaction output from
# the proxy and the direct connection, using invalid URLs may 
# produce unexpected results, including the abnormal termination
# of the testing script.
# 
pub_urls = ['http://www.mit.edu/',
            'http://www.scs.stanford.edu/',];

pub_conc = ['http://www.mit.edu/',];
pub_ab   = ['http://www.mit.edu/',];
ab_conc  = ['-n 20 -c 1', '-n 200 -c 10', '-n 1000 -c 50'];

# timeout_secs - Individual tests will be killed if they do not
# complete within this span of time.
timeout_secs = 45.0
concurrency_tries = [2, 10];
tries = 1

def main():
     global pub_urls

     try:
         proxy_bin = sys.argv[1]
     except IndexError:
         usage()
         sys.exit(2)

     try:
          port = sys.argv[2]
     except IndexError:
          port = str(random.randint(1025, 49151))

     c = 0
     while (c < tries):      
          c += 1
          print 'Binary: %s' % (proxy_bin);
          print 'Running on port %s' % port;
         
          # Start the proxy running in the background
          cid = os.spawnl (os.P_NOWAIT, proxy_bin, proxy_bin, port);

          # Give the proxy time to start up and start listening on the port
          time.sleep(2)
         
          totalcount = 0;
          passcount = 0
          for url in pub_urls:
              totalcount += 1;
              print '### Testing: ' + url
              passed = run_test (compare_url, (url, port), cid)
              if not live_process (cid):
                  print '!!!Proxy process experienced abnormal termination during test- restarting proxy!'
                  (cid, port) = restart_proxy (proxy_bin, port, cid)
                  passed = False

              if passed:
                  print '%s: [PASSED]\n' % url
                  passcount += 1
              else:
                  print '%s: [FAILED]\n' % url

          for count in concurrency_tries:
              for url in pub_conc:
                  totalcount += 1;
                  print '### Testing %d concurrent connects to %s' % (count, url)
                  passed = run_test (concurrent_connect, (count, port, url), cid)
                  if not live_process (cid):
                      print '!!!Proxy process experienced abnormal termination during test- restarting proxy!'
                      (cid, port) = restart_proxy (proxy_bin, port, cid)
                      passed = False
                      
                  if passed:
                      print 'Connect to %s, %d concurrently: [PASSED]\n' % (url, count)
                      passcount += 1
                  else:
                      print 'Connect to %s, %d concurrently: [FAILED]\n' % (url, count)

          for count in concurrency_tries:
              for url in pub_conc:
                  totalcount += 1;
                  print '### Testing %d concurrent fetches to %s' % (count, url)
                  passed = run_test (concurrent_fetch, (count, port, url), cid)
                  if not live_process (cid):
                      print '!!!Proxy process experienced abnormal termination during test- restarting proxy!'
                      (cid, port) = restart_proxy (proxy_bin, port, cid)
                      passed = False

                  if passed:
                      print 'Fetch to %s, %d concurrently: [PASSED]\n' % (url, count)
                      passcount += 1
                  else:
                      print 'Fetch to %s, %d concurrently: [FAILED]\n' % (url, count)


          for count in concurrency_tries:
              for url in pub_conc:
                  totalcount += 1;
                  print '### Testing %d concurrent split fetches' % count
                  passed = run_test (concurrent_fetch_broken, (count, port, url), cid)
                  if not live_process (cid):
                      print '!!!Proxy process experienced abnormal termination during test- restarting proxy!'
                      (cid, port) = restart_proxy (proxy_bin, port, cid)
                      passed = False

                  if passed:
                      print 'Fetch to %s, %d concurrently: [PASSED]\n' % (url, count)
                      passcount += 1
                  else:
                      print 'Fetch to %s, %d concurrently: [FAILED]\n' % (url, count)


          for arg in ab_conc:
              for url in pub_ab:
                  totalcount += 1;
                  print '### Testing apache benchmark on args [%s]' % arg
                  cmdstr = "ab -X 127.0.0.1:%s %s %s" % (port, arg, url);

                  success = False;
                  (sin, sout) = os.popen4 (cmdstr);
                  line = sout.readline ()
                  while line != "" and line != None:
                      print "   ",line.strip ();
                      if line.find ("Failed requests:        0") >= 0:
                          success = True;
                      line = sout.readline ();

                  if success:
                      print '%s with args %s: [PASSED]\n' % (url, arg)
                      passcount += 1;
                  else:
                      print '%s with args %s: [FAILED]\n' % (url, arg)
                      (cid, port) = restart_proxy (proxy_bin, port, cid)

          # Cleanup
          terminate (cid)
          print 'Summary: '
          print '\tType %s: %d of %d tests passed.' % ("multi-process", passcount, totalcount);
          terminate (cid);
          port = str (random.randint (1025, 49151));
          

def usage():
     print "Usage: proxy_tester.py path/to/proxy/binary [port]"
     print "  Omit the port argument for a randomly generated port."

def run_test(test, args, childid):
     '''
     Run a single test function, monitoring its execution with a timer thread.

     * test: A function to execute.  Should take a tuple as its sole 
     argument and return True for a passed test, and False otherwise.
     * args: Tuple that contains arguments to the test function
     * childid: Process ID of the running proxy

     The amount of time that the monitor waits before killing
     the proxy process can be set by changing timeout_secs at the top of this 
     file.
     
     Returns True for a passed test, False otherwise.
     '''
     monitor = threading.Timer(timeout_secs, do_timeout, [childid])
     monitor.start()
     if not test(args):
          passed = False
     else:
          passed = True
     monitor.cancel()
     return passed


def concurrent_connect(argtuple):
    global _connected;

    count, port, url = argtuple;

    pool = ThreadPool (count);
    for cnt in range(count):
        pool.queueTask (do_connect, ('localhost', port));
    pool.joinAll ();

    result = compare_url ((url, port));

    for item in _connected:
        if item[1] == True:
            item[0].close ();
        else:
            result = False;
    _connected = [];
    return result;


def concurrent_fetch (argtuple):
    global _connected;
    global _success;

    _success = 0;

    count, port, url = argtuple;

    pool = ThreadPool (count);
    for cnt in range(count):
        pool.queueTask (do_http_send, ('localhost', port, url));
    pool.joinAll ();

    result = compare_url ((url, port));

    pool = ThreadPool (count);
    for item in _connected:
        if item[1] == True:
            pool.queueTask (do_http_read, (item[0], item[2]));
    pool.joinAll ();

    _connected = [];
    return _success == count and result;

def concurrent_fetch_broken (argtuple):
    global _connected;
    global _success;

    _success = 0;

    count, port, url = argtuple;

    pool = ThreadPool (count);
    for cnt in range(count):
        pool.queueTask (do_http_send_partial, ('localhost', port, url));
    pool.joinAll ();

    result = compare_url ((url, port));

    connected = _connected;

    pool = ThreadPool (count);
    for item in connected:
        if item[1] == True:
            pool.queueTask (do_http_send_finish, item[0]);
    pool.joinAll ();

    pool = ThreadPool (count);
    for item in _connected:
        if item[1] == True:
            pool.queueTask (do_http_read, (item[0], item[2]));
    pool.joinAll ();

    _connected = [];
    return _success == count and result;


def compare_url(argtuple):
     '''
     Compare proxy output to the output from a direct server transaction.
     
     A simple sample test: download a web page via the proxy, and then fetch the 
     same page directly from the server.  Compare the two pages for any
     differences, ignoring the Date header field if it is set.
     
     Argument tuples is in the form (url, port), where url is the URL to open, and
     port is the port the proxy is running on.
     '''
     (url, port) = argtuple
     urldata = urlparse.urlparse(url)
     try:
          (host, hostport) = urldata[1].split(':')
     except ValueError:
          host = urldata[1]
          hostport = 80

     # Retrieve via proxy
     try:
          proxy_data = get_data('localhost', port, url)
     except socket.error:
          print '!!!! Socket error while attempting to talk to proxy!'  
          return False

     # Retrieve directly
     direct_data = get_direct(host, hostport, urldata[2])

     passed = True
     for (proxy, direct) in zip(proxy_data, direct_data):
          if proxy != direct and not (proxy.startswith('Date') and direct.startswith('Date')) \
                  and not (proxy.startswith('Expires') and direct.startswith('Expires')) \
                  and not (proxy.startswith('Cache-Control') and direct.startswith('Cache-Control')):
               print 'compare_url failed on %s' % url
               print 'Proxy:  %s' % proxy
               print 'Direct: %s' % direct
               passed = False
               break;

     return passed

def get_direct(host, port, url):
     '''Retrieve a URL using direct HTTP/1.0 GET.'''
     getstring = 'GET %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n'
     data = http_exchange(host, port,  getstring % (url, host))
     return data.split('\n')

def get_data(host, port, url):
     '''Retrieve a URL using proxy HTTP/1.0 GET.'''
     getstring = 'GET %s HTTP/1.0\r\nConnection: close\r\n\r\n'
     data = http_exchange(host, port,  getstring % url)
     return data.split('\n')


_connected = [];
_success = 0;

def do_connect (argtuple):
    global _connected;
    host, port = argtuple;
    try:
        conn = telnetlib.Telnet()
        conn.open(host, port)
        _connected.append ((conn, True));
    except socket.error:
        print '!!! do_connect: Socket error while attempting to talk to proxy: %s port %s'  % (host, port);
        _connected.append ((conn, False));


def do_http_send (argtuple):
    global _connected;
    host, port, url = argtuple;
    try:
        data = 'GET %s HTTP/1.0\r\nConnection: close\r\n\r\n' % url;
        conn = telnetlib.Telnet()
        conn.open(host, port)
        conn.write(data)
        _connected.append ((conn, True, url));
    except socket.error:
        print '!!!! do_http_send: Socket error while attempting to talk to proxy: %s port %s'  % (host, port);
        _connected.append ((conn, False, url));


def do_http_read (argtuple):
    global _success;

    conn, url = argtuple;
    try:
        proxy_data = conn.read_all().split ('\n');
        conn.close ();

        urldata = urlparse.urlparse (url)
        try:
            (host, hostport) = urldata[1].split(':')
        except ValueError:
            host = urldata[1];
            hostport = 80

        # Retrieve directly
        direct_data = get_direct (host, hostport, urldata[2])

        passed = True
        for (proxy, direct) in zip(proxy_data, direct_data):
          if proxy != direct and not (proxy.startswith('Date') and direct.startswith('Date')) \
                  and not (proxy.startswith('Expires') and direct.startswith('Expires')) \
                  and not (proxy.startswith('Cache-Control') and direct.startswith('Cache-Control')):
                print 'do_http_read failed on %s' % url
                print 'Proxy:  %s' % proxy
                print 'Direct: %s' % direct
                passed = False
                break;

        if passed:
            _success += 1;
    except socket.error:
        print '!!!! do_http_read: Socket error while attempting to talk to proxy';


def do_http_send_partial (argtuple):
    global _connected;
    host, port, url = argtuple;
    try:
        data = 'GET %s ' % url;
        conn = telnetlib.Telnet()
        conn.open(host, port)
        conn.write(data)
        _connected.append ((conn, True, url));
    except socket.error:
        print '!!!! do_http_send_partial: Socket error while attempting to talk to proxy: %s port %s'  % (host, port);
        _connected.append ((conn, False, url));

def do_http_send_finish (conn):
    try:
        data = 'HTTP/1.0\r\nConnection: close\r\n\r\n';
        conn.write(data)
    except socket.error:
        print '!!!! do_http_send_finish: Socket error while attempting to talk to proxy';

def http_exchange(host, port, data):
     conn = telnetlib.Telnet()
     conn.open(host, port)
     conn.write(data)
     ret_data = conn.read_all()
     conn.close()
     return ret_data

def live_process(pid):
     '''Check that a process is still running.'''
     try:
          os.kill(pid, 0)
          return True
     except OSError:
          return False

def do_timeout(id):
     '''Callback function run by the monitor threads to kill a long-running operation.'''
     print '!!!! Proxy transaction timed out after %d seconds' % timeout_secs
     terminate(id)

def terminate(id):
     '''Stops and cleans up a running child process.'''
     if live_process (id) == True:
         os.kill(id, signal.SIGINT)
         time.sleep (3)
         os.kill(id, signal.SIGKILL)
         try:
             os.waitpid(id, 0)
         except OSError:
             pass

def restart_proxy(binary, oldport, oldcid):
     '''Restart the proxy on a new port number.'''
     terminate (oldcid);
     newport = str (int(oldport) + 1)
     cid = os.spawnl(os.P_NOWAIT, binary, binary, newport);
     time.sleep(3)
     return (cid, newport)

if __name__ == '__main__':
     main()

