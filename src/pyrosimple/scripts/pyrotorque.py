# -*- coding: utf-8 -*-
# pylint: disable=attribute-defined-outside-init
""" rTorrent queue manager & daemon.

    Copyright (c) 2012 The PyroScope Project <pyroscope.project@gmail.com>
"""
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os
import shlex
import signal
import sys
import time

from pathlib import Path
from typing import Dict

from apscheduler.schedulers.background import BackgroundScheduler
from daemon import DaemonContext
from daemon.pidfile import TimeoutPIDLockFile

from pyrosimple import config, error
from pyrosimple.scripts.base import ScriptBase, ScriptBaseWithConfig
from pyrosimple.util import logutil, pymagic

class RtorrentQueueManager(ScriptBaseWithConfig):
    ### Keep things wrapped to fit under this comment... ##############################
    """
    rTorrent queue manager & daemon.
    """

    # argument description for the usage information
    ARGS_HELP = ""

    OPTIONAL_CFG_FILES = ["torque.ini"]

    POLL_TIMEOUT = 1.0

    RUNTIME_DIR = os.getenv("XDG_RUNTIME_DIR") or "~/.pyrosimple/run/"

    def add_options(self):
        """Add program options."""
        super().add_options()
        self.jobs: Dict = {}
        self.httpd = None

        # basic options
        self.add_bool_option(
            "-n",
            "--dry-run",
            help="advise jobs not to do any real work, just tell what would happen",
        )
        self.add_bool_option(
            "--no-fork",
            "--fg",
            help="Don't fork into background (stay in foreground and log to console)",
        )
        self.add_value_option(
            "--run-once", "JOB", help="run the specified job once in the foreground"
        )
        self.add_bool_option("--stop", help="Stop running daemon")
        self.add_bool_option(
            "--restart", help="Stop running daemon, then fork into background"
        )
        self.add_bool_option("-?", "--status", help="Check daemon status")
        self.add_value_option(
            "--pid-file",
            "PATH",
            help="file holding the process ID of the daemon, when running in background",
        )
        self.add_value_option(
            "--guard-file", "PATH", help="guard file for the process watchdog"
        )

    def _parse_schedule(self, schedule):
        """Parse a job schedule."""
        result = {}

        for param in shlex.split(str(schedule)):  # do not feed unicode to shlex
            try:
                key, val = param.split("=", 1)
                if key == "jitter":
                    val = int(val)
            except (TypeError, ValueError):
                self.fatal("Bad param '%s' in job schedule '%s'" % (param, schedule))
            else:
                result[key] = val

        return result

    def _validate_config(self):
        """Handle and check configuration."""

        for name, params in config.settings.TORQUE.items():
            for key in ("handler", "schedule"):
                if key not in params:
                    self.fatal(
                        "Job '%s' is missing the required '%s' parameter"
                        % (name, key)
                    )
            self.jobs[name] = dict(params)
            if params.get('active', False):
                self.jobs[name]['handler'] = pymagic.import_name(params.handler)
            self.jobs[name]['schedule'] = self._parse_schedule(params.get('schedule'))

    def _add_jobs(self):
        """Add configured jobs."""
        for name, params in self.jobs.items():
            if params['active']:
                params['handler'] = params['handler'](params)
                self.sched.add_job(
                    params['handler'].run, name=name, trigger="cron", **params['schedule']
                )

    def _run_forever(self):
        """Run configured jobs until termination request."""
        while True:
            try:
                time.sleep(self.POLL_TIMEOUT)
            except KeyboardInterrupt as exc:
                self.LOG.info("Termination request received (%s)", exc)
                break
            except SystemExit as exc:
                self.return_code = exc.code or 0
                self.LOG.info("System exit (RC=%r)", self.return_code)
                break
            else:
                # Idle work
                # self.LOG.warning("IDLE %s %r" % (self.options.guard_file, os.path.exists(self.options.guard_file)))
                if self.options.guard_file and not os.path.exists(
                    self.options.guard_file
                ):
                    self.LOG.warning(
                        "Guard file '%s' disappeared, exiting!", self.options.guard_file
                    )
                    break

    def mainloop(self):
        """The main loop."""
        self._validate_config()

        # Defaults for process control paths
        if not self.options.no_fork and not self.options.guard_file:
            self.options.guard_file = Path(
                self.RUNTIME_DIR, "pyrotorque.guard"
            ).expanduser()
        if not self.options.pid_file:
            self.options.pid_file = TimeoutPIDLockFile(
                Path(self.RUNTIME_DIR, "pyrotorque.pid").expanduser()
            )

        # Process control
        if self.options.status or self.options.stop or self.options.restart:
            if self.options.pid_file.is_locked():
                running, pid = True, self.options.pid_file.read_pid()
            else:
                running, pid = False, 0

            if self.options.stop or self.options.restart:
                if running:
                    os.kill(pid, signal.SIGTERM)
                    self.LOG.debug("Process #%d sent SIGTERM.", pid)

                    # Wait for termination (max. 10 secs)
                    for _ in range(100):
                        if not self.options.pid_file.is_locked():
                            running = False
                            break
                        time.sleep(0.1)

                    self.LOG.info("Process #%d stopped.", pid)
                elif pid:
                    self.LOG.info("Process #%d NOT running anymore.", pid)
                else:
                    self.LOG.info(
                        "No pid file '%s'", (self.options.pid_file or "<N/A>")
                    )
            else:
                self.LOG.info(
                    "Process #%d %s running.", pid, "UP and" if running else "NOT"
                )

            if self.options.stop:
                self.return_code = error.EX_OK if running else error.EX_UNAVAILABLE
                return

        # Check for guard file and running daemon, abort if not OK
        if self.options.guard_file and not os.path.exists(self.options.guard_file):
            raise EnvironmentError(
                "Guard file '%s' not found, won't start!" % self.options.guard_file
            )

        # Check if we only need to run once
        if self.options.run_once:
            params = self.jobs[self.options.run_once]
            params['handler_copy'] = params.get('handler')(params)
            params['handler_copy'].run()
            sys.exit(0)

        dcontext = DaemonContext(
            detach_process=False,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        # Detach, if not disabled via option
        if (
            not self.options.no_fork
        ):  # or getattr(sys.stdin, "isatty", lambda: False)():
            dcontext.detach_process = True
            dcontext.stdin = None
            dcontext.stderr = logutil.get_logfile()
            dcontext.stdout = logutil.get_logfile()
            dcontext.pidfile = self.options.pid_file

        with dcontext:
            if dcontext.pidfile:
                print(dcontext.pidfile)
            # Set up services
            self.sched = BackgroundScheduler()

            # Run services
            self.sched.start()
            try:
                self._add_jobs()
                # TODO: daemonize here, or before the scheduler starts?
                self._run_forever()
            finally:
                self.sched.shutdown()


def run():  # pragma: no cover
    """The entry point."""
    ScriptBase.setup()
    RtorrentQueueManager().run()


if __name__ == "__main__":
    run()
