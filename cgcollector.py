#!/usr/bin/env python3
'''cgcollector: A configurable cgroup statistics collector for collectd.'''

import logging
import multiprocessing as mp
import os
import sched
import signal
import socket
import sys
import time

from glob import glob
from queue import Full as QueueFull
from random import random

_VERSION = ('0', '0', '1')

_TYPE_CPU_TIME = 0
_TYPE_CPU_PERCENT = 1
_TYPE_MEMORY = 2
_TYPE_PIDS = 3
_TYPE_BLKIO_IOPS = 4
_TYPE_BLKIO_OCTETS = 5

_TYPE_CPU = _TYPE_CPU_TIME

_CONTROLLERS = [
    'cpu',
    'mem',
    'blkio',
    'pids'
]

# This is a list of signals we catch and die on.
_CATCH_SIGNALS = [
    signal.SIGQUIT,
    signal.SIGABRT,
    signal.SIGALRM,
    signal.SIGTERM,
    signal.SIGCHLD,
    signal.SIGVTALRM,
    signal.SIGPROF
]

# And this lists ones we explicitly ignore.
_IGNORE_SIGNALS = [
    signal.SIGHUP,
    signal.SIGUSR1,
    signal.SIGUSR2
]

def _rusleep():
    '''Sleep for a small pseudo-random amount of time.'''
    return time.sleep(random() * 0.001)

def collect_cpuacct(group, config, queue, pdata):
    '''Collect cpuacct stats for the given cgroup.'''
    logging.debug('Collecting cpu data for %s', group)
    tstamp = time.time()
    data = [None, None, 0, 0]
    statpath = os.path.normpath(os.path.join(config['cpu']['path'], group, 'cpuacct.stat'))
    tmp = None
    try:
        with open(statpath, 'r') as stats:
            tmp = stats.read()
    except (OSError, IOError):
        pass
    logging.debug('Processing cpu data for %s', group)
    if tmp:
        tmp = tmp.splitlines()
        data[0] = int(tmp[0].split()[-1])
        data[1] = int(tmp[1].split()[-1])
        if config['cpu']['report-percent']:
            if not (group + '.sys') in pdata.keys() or \
                not (group + '.user') in pdata.keys():
                prevsys = data[0]
                prevuser = data[1]
            else:
                prevsys = pdata[group + '.sys']
                prevuser = pdata[group + '.user']
            pdata[group + '.sys'] = data[0]
            pdata[group + '.user'] = data[1]
            if not prevsys == 'U':
                data[2] = (data[0] - prevsys) / config['period']
            if not prevuser == 'U':
                data[3] = (data[1] - prevsys) / config['period']
            if config['cpu']['global-percent']:
                data[2] = data[2] / os.cpu_count()
                data[3] = data[3] / os.cpu_count()
    elif config['cpu']['report-percent']:
        pdata[group + '.sys'] = 0
        pdata[group + '.user'] = 0
    _rusleep()
    try:
        if config['cpu']['report-time']:
            msg = (tstamp, group, data[0:2], _TYPE_CPU_TIME)
            queue.put(msg)
            logging.debug('Pushed: %s', repr(msg))
        if config['cpu']['report-percent']:
            msg = (tstamp, group, data[2:4], _TYPE_CPU_PERCENT)
            queue.put(msg)
            logging.debug('Pushed: %s', repr(msg))
    except QueueFull:
        logging.warning('Sample lost because queue is full.')
    return True

def collect_mem(group, config, queue):
    '''Collect memory stats for the given cgroup.'''
    logging.debug('Collecting mem data for %s', group)
    tstamp = time.time()
    data = [0, 0, 0]
    statpaths = [
        os.path.join(config['mem']['path'], group, 'memory.usage_in_bytes'),
        os.path.join(config['mem']['path'], group, 'memory.kmem.usage_in_bytes'),
        os.path.join(config['mem']['path'], group, 'memory.memsw.usage_in_bytes')
    ]
    for index in range(0, len(statpaths)):
        try:
            with open(statpaths[index], 'r') as stats:
                data[index] = stats.read()
        except (OSError, IOError):
            pass
    logging.debug('Processing memory data for %s', group)
    data[0] = int(data[0])
    data[1] = int(data[1])
    data[2] = max(int(data[2]) - data[0], 0)
    _rusleep()
    try:
        msg = (tstamp, group, data, _TYPE_MEMORY)
        queue.put(msg)
        logging.debug('Pushed: %s', repr(msg))
    except QueueFull:
        logging.warning('Sample lost because queue is full.')
    return True

def collect_aggregate_blkio_stats(data):
    '''Return total readn and write stats out of a blkio controller stats file.'''
    stats = [0, 0]
    data = data.splitlines()
    for line in data:
        line = line.split()
        if line[1] == 'Read':
            stats[0] += int(line[2])
        elif line[1] == 'Write':
            stats[1] += int(line[2])
    return stats

def collect_blkio_octets(group, config, queue):
    '''Collect blkio stats for the given cgroup.'''
    logging.debug('Collecting blkio_octets data for %s', group)
    tstamp = time.time()
    data = [0, 0]
    statpath = os.path.join(config['blkio']['path'], group, 'blkio.throttle.io_service_bytes')
    tmp = None
    try:
        with open(statpath, 'r') as stats:
            tmp = stats.read()
    except (OSError, IOError):
        pass
    logging.debug('Processing blkio_octets data for %s', group)
    data = collect_aggregate_blkio_stats(tmp)
    _rusleep()
    try:
        msg = (tstamp, group, data, _TYPE_BLKIO_OCTETS)
        queue.put(msg)
        logging.debug('Pushed: %s', repr(msg))
    except QueueFull:
        logging.warning('Sample lost because queue is full.')
    return True

def collect_blkio_iops(group, config, queue):
    '''Collect blkio stats for the given cgroup.'''
    logging.debug('Collecting blkio_iops data for %s', group)
    tstamp = time.time()
    data = [0, 0]
    statpath = os.path.join(config['blkio']['path'], group, 'blkio.throttle.io_serviced')
    tmp = None
    try:
        with open(statpath, 'r') as stats:
            tmp = stats.read()
    except (OSError, IOError):
        pass
    logging.debug('Processing blkio_iops data for %s', group)
    data = collect_aggregate_blkio_stats(tmp)
    _rusleep()
    try:
        msg = (tstamp, group, data, _TYPE_BLKIO_IOPS)
        queue.put(msg)
        logging.debug('Pushed: %s', repr(msg))
    except QueueFull:
        logging.warning('Sample lost because queue is full.')
    return True

def collect_pids(group, config, queue):
    '''Collect pids stats for the given cgroup.'''
    logging.debug('Collecting pids data for %s', group)
    tstamp = time.time()
    statpath = os.path.join(config['pids']['path'], group, 'pids.current')
    data = None
    _rusleep()
    try:
        with open(statpath, 'r') as stats:
            data = int(stats.read())
    except (OSError, IOError):
        pass
    logging.debug('Processing pids data for %s', group)
    try:
        queue.put((tstamp, group, (data,), _TYPE_PIDS))
    except QueueFull:
        logging.warning('Sample lost because queue is full.')
    return True

def _collectd_submit(config, queue):
    '''Push data from the queue to collectd.'''
    host = config['host']
    sanitized = dict()
    with socket.socket(family=socket.AF_UNIX, type=socket.SOCK_STREAM) as sock:
        try:
            sock.connect(config['socket'])
        except OSError:
            sys.exit(-1)
        logging.info('Connected to collectd via %s', config['socket'])
        while True:
            data = queue.get(True, None)
            logging.debug('submit: recieved data %s', repr(data))
            if data[3] == _TYPE_CPU_TIME:
                plugin = config['plugin'] + 'cpu'
                datatype = 'cgstats_cpu'
                stats = '{0}:{1}'.format(*data[2])
            elif data[3] == _TYPE_CPU_PERCENT:
                plugin = config['plugin'] + 'cpu'
                datatype = 'cgstats_cpu_percent'
                stats = '{0}:{1}'.format(*data[2])
            elif data[3] == _TYPE_PIDS:
                plugin = config['plugin'] + 'pids'
                datatype = 'cgstats_pid'
                stats = str(data[2][0])
            elif data[3] == _TYPE_MEMORY:
                plugin = config['plugin'] + 'mem'
                datatype = 'cgstats_mem'
                stats = '{0}:{1}:{2}'.format(*data[2])
            elif data[3] == _TYPE_BLKIO_OCTETS:
                plugin = config['plugin'] + 'blkio'
                datatype = 'cgstats_blk_octets'
                stats = '{0}:{1}'.format(*data[2])
            elif data[3] == _TYPE_BLKIO_IOPS:
                plugin = config['plugin'] + 'blkio'
                datatype = 'cgstats_blk_iops'
                stats = '{0}:{1}'.format(*data[2])
            else:
                logging.warning('Unknown data sample type, dropping sample.')
                continue
            if data[1] not in sanitized.keys():
                sanitized[data[1]] = data[1].lstrip('/').replace('.', '_').replace('-', '_').replace('/', '_')
            instance = sanitized[data[1]]
            msghead = 'PUTVAL {0}/{1}-{2}/{3}'.format(host, plugin, instance, datatype)
            msgdata = '{0}:{1}'.format(data[0], stats)
            message = '{0} {1}\n'.format(msghead, msgdata)
            logging.debug('Sending: %s', message)
            sock.sendall(message.encode())
            result = sock.recv(4096).decode()
            if not result.startswith('0 Success'):
                logging.warning('Error sending data to collectd: %s', result)

def check_config(config):
    '''Fix-up the config to include all the keys we need.

       This also merges the groups sections properly, and raises an error
       if no cgroups are to be monitored in any of the controllers.'''
    _controllers = list()
    logging.debug('Initial config: \n%s', repr(config))
    # Global configuration item defaults.
    if not 'queue-size' in config.keys():
        config['queue-size'] = 256
    if not 'parallel' in config.keys():
        config['parallel'] = len(os.sched_getaffinity(0))
        logging.info('Using %s cpus.', config['parallel'])
    if not 'plugin' in config.keys():
        config['plugin'] = 'cg_'
    if not 'host' in config.keys():
        config['host'] = socket.gethostname()
        logging.info('Hostname is %s', config['host'])
    # Basic sanity checks for the controllers.
    for controller in _CONTROLLERS:
        if controller in config.keys():
            if not 'groups' in config[controller].keys():
                config[controller]['groups'] = list()
            if not 'path' in config[controller]:
                logging.warning('No path configured for ' + controller + ' controller, not monitoring this controller.')
                del config[controller]
            else:
                _controllers.append(controller)
    # Merge the global groups section in for each controller.
    if 'groups' in config.keys():
        if not isinstance(config['groups'], list):
            logging.error('Invalid configuration (\'groups\' section is wrong type.')
            sys.exit(1)
        for item in config['groups']:
            for controller in _CONTROLLERS:
                if controller in config.keys() and not item in config[controller]['groups']:
                    config[controller]['groups'].append(item)
    logging.debug('Merged config:\n%s', repr(config))
    # Bail if nothing would be monitored.
    monitor = False
    for controller in _controllers:
        if len(config[controller]['groups']) > 0:
            logging.info('%s groups matches set in %s for monitoring', len(config[controller]['groups']), controller)
            monitor = True
    if not monitor:
        logging.error('No cgroups configured for monitoring.')
        sys.exit(1)
    # Controller specific configuration item defaults.
    if 'cpu' in config.keys():
        if not 'report-time' in config['cpu'].keys():
            config['cpu']['report-time'] = True
        if not 'report-percent' in config['cpu'].keys():
            config['cpu']['report-percent'] = False
        if not 'global-percent' in config['cpu'].keys():
            config['cpu']['global-percent'] = False
    if 'blkio' in config.keys():
        if not 'report-octets' in config['blkio'].keys():
            config['blkio']['report-octets'] = True
        if not 'report-iops' in config['blkio'].keys():
            config['blkio']['report-iops'] = True
    return config

def expand_groups(groups, path):
    '''Perform filename globbing and deduplication on 'groups'.'''
    newgroups = list()
    for item in groups:
        check = os.path.join(path, item)
        for result in glob(check):
            result = result.replace(path, '', 1).lstrip('/')
            if not result in newgroups:
                newgroups.append(result)
    return newgroups

def trigger(scheduler, config, pool, submit, queue, pdata):
    '''Trigger data collection.

       This first schedules the next data collection event, then checks
       that the submission process is still alive, and then dispatches
       the data collection tasks to the process pool.'''
    nextevt = time.monotonic() + config['period']
    if not submit.is_alive():
        return False
    scheduler.enterabs(nextevt, 0, trigger, argument=(scheduler, config, pool, submit, queue, pdata))
    if 'cpu' in config.keys():
        groups = expand_groups(config['cpu']['groups'], config['cpu']['path'])
        for group in groups:
            logging.debug('Dispatching collection for %s in %s controller', group, 'cpu')
            pool.apply(collect_cpuacct, (group, config, queue, pdata))
    if 'mem' in config.keys():
        groups = expand_groups(config['mem']['groups'], config['mem']['path'])
        for group in groups:
            logging.debug('Dispatching collection for %s in %s controller', group, 'mem')
            pool.apply(collect_mem, (group, config, queue))
    if 'pids' in config.keys():
        groups = expand_groups(config['pids']['groups'], config['pids']['path'])
        for group in groups:
            logging.debug('Dispatching collection for %s in %s controller', group, 'pids')
            pool.apply(collect_pids, (group, config, queue))
    if 'blkio' in config.keys() and config['blkio']['report-octets']:
        groups = expand_groups(config['blkio']['groups'], config['blkio']['path'])
        for group in groups:
            logging.debug('Dispatching collection for %s in %s controller', group, 'blkio_octets')
            pool.apply(collect_blkio_octets, (group, config, queue))
    if 'blkio' in config.keys() and config['blkio']['report-iops']:
        groups = expand_groups(config['blkio']['groups'], config['blkio']['path'])
        for group in groups:
            logging.debug('Dispatching collection for %s in %s controller', group, 'blkio_iops')
            pool.apply(collect_blkio_octets, (group, config, queue))
    return True

def _sighandler(signum, frame):
    '''Handle most fatal signals.'''
    pool.close()
    pool.join()
    if submit.is_alive():
        submit.terminate()
    submit.join()
    sys.exit(0)

def run(config):
    '''Main program logic.'''
    global submit
    global pool
    ob = mp.Manager()
    queue = ob.Queue(config['queue-size'])
    pdata = ob.dict()
    submit = mp.Process(target=_collectd_submit, args=(config, queue))
    submit.daemon = True
    pool = mp.Pool(config['parallel'])
    scheduler = sched.scheduler()
    scheduler.enterabs(2, 0, trigger, argument=(scheduler, config, pool, submit, queue, pdata))
    submit.start()
    logging.info('Initialization done, beginning data collection.')
    # trigger() re-arms itself in the scheduler as long as the submission
    # process is still running, so this will block until either we get hit
    # with a fatal signal, or the submission process dies for some reason,
    # at which point we clean up and exit.
    for item in _IGNORE_SIGNALS:
        signal.signal(item, signal.SIG_IGN)
    for item in _CATCH_SIGNALS:
        signal.signal(item, _sighandler)
    try:
        scheduler.run(blocking=True)
    finally:
        pool.close()
        pool.join()
        if submit.is_alive():
            submit.terminate()
        submit.join()
    return 0


if __name__ == '__main__':
    import yaml
    mp.set_start_method('fork')
    with open(sys.argv[1]) as conf:
        CONFIG = yaml.safe_load(conf)
    if 'debug' in CONFIG.keys():
        logging.basicConfig(format='%(asctime)s: %(message)s', level=logging.DEBUG, datefmt='%Y-%m-%d %H:%M:%S')
    else:
        logging.basicConfig(format='%(asctime)s: %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
    sys.exit(run(check_config(CONFIG)))
