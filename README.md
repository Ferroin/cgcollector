# cgcollector #
cgcollector is a tool for collecting statistics from Linux control
groups, and submitting them to collectd.  The general idea is similar
to collectd's own `cgroup` plugin, albeit with a lot more flexibility.

## Features ##
* Supports collection of both time and percentages for both user and
  system execution via the cpuacct controller.
* Supports tracking user memory, kernel memory, and swap usage via the
  memory cgroup.
* Supports tracking byte rates and IOPS via the blkio controller.
* Supports tracking process counts via the pids controller.
* Allows matching different sets of cgroups for each controller.
* Allows matching cgroups using shell style filename expansion.
* Runs independent of collectd, so you don't have to run collectd as
  root to collect data from the cgroups.
* Allows an arbitrary level of parallelization in the collection process.
* Ignores cgroups it's been toold to collect data from which don't exist.
* Supports arbitrary mount locations for each controller.

## Dependencies ##
* Python 3.6 or higher.
* PyYAML 3.12 or higher (it may work with earlier versions).
* A version of collectd which supports the unixsock module (required to
  submit data to collectd).

Additionally, your system has to support cgroups and needs to have them
set up before cgcollector starts.

## Usage ##
Using cgcollector is pretty simple.  All the configuration is done
via a YAML config file which then gets passed as the only argument
to cgcollector.  A sample config file with documentation of all the
options can be found in config.yml in the source.  You will need to have
collectd's unixsock plugin setup so that cgcollector can actually send
data to collectd.  You will also need to add the included types.db file
to the list of type databases loaded by collectd.  Some general info is
logged to stdout during operation.  Note that if you want cgcollector
to run as a daemon, you will need to use some external tool to do this.
