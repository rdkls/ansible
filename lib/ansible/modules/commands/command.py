#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2012, Michael DeHaan <michael.dehaan@gmail.com>, and others
# Copyright: (c) 2016, Toshio Kuratomi <tkuratomi@ansible.com>
#
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['stableinterface'],
                    'supported_by': 'core'}

DOCUMENTATION = '''
---
module: command
short_description: Executes a command on a remote node
version_added: historical
description:
     - The C(command) module takes the command name followed by a list of space-delimited arguments.
     - The given command will be executed on all selected nodes. It will not be
       processed through the shell, so variables like C($HOME) and operations
       like C("<"), C(">"), C("|"), C(";") and C("&") will not work (use the M(shell)
       module if you need these features).
     - For Windows targets, use the M(win_command) module instead.
options:
  free_form:
    description:
      - The command module takes a free form command to run.  There is no parameter actually named 'free form'.
        See the examples!
    required: yes
  argv:
    description:
      - Allows the user to provide the command as a list vs. a string.  Only the string or the list form can be
        provided, not both.  One or the other must be provided.
    version_added: "2.6"
  creates:
    description:
      - A filename or (since 2.0) glob pattern, when it already exists, this step will B(not) be run.
  removes:
    description:
      - A filename or (since 2.0) glob pattern, when it does not exist, this step will B(not) be run.
    version_added: "0.8"
  chdir:
    description:
      - Change into this directory before running the command.
    version_added: "0.6"
  warn:
    description:
      - If command_warnings are on in ansible.cfg, do not warn about this particular line if set to C(no).
    type: bool
    default: 'yes'
    version_added: "1.8"
  stdin:
    version_added: "2.4"
    description:
      - Set the stdin of the command directly to the specified value.
notes:
    -  If you want to run a command through the shell (say you are using C(<), C(>), C(|), etc), you actually want the M(shell) module instead.
       Parsing shell metacharacters can lead to unexpected commands being executed if quoting is not done correctly so it is more secure to
       use the C(command) module when possible.
    -  " C(creates), C(removes), and C(chdir) can be specified after the command.
       For instance, if you only want to run a command if a certain file does not exist, use this."
    -  Check mode is supported when passing C(creates) or C(removes). If running in check mode and either of these are specified, the module will
       check for the existence of the file and report the correct changed status. If these are not supplied, the task will be skipped.
    -  The C(executable) parameter is removed since version 2.4. If you have a need for this parameter, use the M(shell) module instead.
    -  For Windows targets, use the M(win_command) module instead.
author:
    - Ansible Core Team
    - Michael DeHaan
'''

EXAMPLES = '''
- name: return motd to registered var
  command: cat /etc/motd
  register: mymotd

- name: Run the command if the specified file does not exist.
  command: /usr/bin/make_database.sh arg1 arg2
  args:
    creates: /path/to/database

# You can also use the 'args' form to provide the options.
- name: This command will change the working directory to somedir/ and will only run when /path/to/database doesn't exist.
  command: /usr/bin/make_database.sh arg1 arg2
  args:
    chdir: somedir/
    creates: /path/to/database

- name: use argv to send the command as a list.  Be sure to leave command empty
  command:
  args:
    argv:
      - echo
      - testing

- name: safely use templated variable to run command. Always use the quote filter to avoid injection issues.
  command: cat {{ myfile|quote }}
  register: myoutput
'''

RETURN = '''
cmd:
  description: the cmd that was run on the remote machine
  returned: always
  type: list
  sample:
  - echo
  - hello
delta:
  description: cmd end time - cmd start time
  returned: always
  type: string
  sample: 0:00:00.001529
end:
  description: cmd end time
  returned: always
  type: string
  sample: '2017-09-29 22:03:48.084657'
start:
  description: cmd start time
  returned: always
  type: string
  sample: '2017-09-29 22:03:48.083128'
'''

import datetime
import glob
import os
import shlex

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils._text import to_native
from ansible.module_utils.common.collections import is_iterable


def check_command(module, commandline):
    arguments = {'chown': 'owner', 'chmod': 'mode', 'chgrp': 'group',
                 'ln': 'state=link', 'mkdir': 'state=directory',
                 'rmdir': 'state=absent', 'rm': 'state=absent', 'touch': 'state=touch'}
    commands = {'curl': 'get_url or uri', 'wget': 'get_url or uri',
                'svn': 'subversion', 'service': 'service',
                'mount': 'mount', 'rpm': 'yum, dnf or zypper', 'yum': 'yum', 'apt-get': 'apt',
                'tar': 'unarchive', 'unzip': 'unarchive', 'sed': 'replace, lineinfile or template',
                'dnf': 'dnf', 'zypper': 'zypper'}
    become = ['sudo', 'su', 'pbrun', 'pfexec', 'runas', 'pmrun', 'machinectl']
    if isinstance(commandline, list):
        command = commandline[0]
    else:
        command = commandline.split()[0]
    command = os.path.basename(command)

    disable_suffix = "If you need to use command because {mod} is insufficient you can add" \
                     " warn=False to this command task or set command_warnings=False in" \
                     " ansible.cfg to get rid of this message."
    substitutions = {'mod': None, 'cmd': command}

    if command in arguments:
        msg = "Consider using the {mod} module with {subcmd} rather than running {cmd}.  " + disable_suffix
        substitutions['mod'] = 'file'
        substitutions['subcmd'] = arguments[command]
        module.warn(msg.format(**substitutions))

    if command in commands:
        msg = "Consider using the {mod} module rather than running {cmd}.  " + disable_suffix
        substitutions['mod'] = commands[command]
        module.warn(msg.format(**substitutions))

    if command in become:
        module.warn("Consider using 'become', 'become_method', and 'become_user' rather than running %s" % (command,))


def main():

    # the command module is the one ansible module that does not take key=value args
    # hence don't copy this one if you are looking to build others!
    module = AnsibleModule(
        argument_spec=dict(
            _raw_params=dict(),
            _uses_shell=dict(type='bool', default=False),
            argv=dict(type='list'),
            chdir=dict(type='path'),
            executable=dict(),
            creates=dict(type='path'),
            removes=dict(type='path'),
            # The default for this really comes from the action plugin
            warn=dict(type='bool', default=True),
            stdin=dict(required=False),
        ),
        supports_check_mode=True,
    )
    shell = module.params['_uses_shell']
    chdir = module.params['chdir']
    executable = module.params['executable']
    args = module.params['_raw_params']
    argv = module.params['argv']
    creates = module.params['creates']
    removes = module.params['removes']
    warn = module.params['warn']
    stdin = module.params['stdin']

    if not shell and executable:
        module.warn("As of Ansible 2.4, the parameter 'executable' is no longer supported with the 'command' module. Not using '%s'." % executable)
        executable = None

    if (not args or args.strip() == '') and not argv:
        module.fail_json(rc=256, msg="no command given")

    if args and argv:
        module.fail_json(rc=256, msg="only command or argv can be given, not both")

    if not shell and args:
        args = shlex.split(args)

    args = args or argv

    # All args must be strings
    if is_iterable(args, include_strings=False):
        args = [to_native(arg, errors='surrogate_or_strict', nonstring='simplerepr') for arg in args]

    if chdir:
        chdir = os.path.abspath(chdir)
        os.chdir(chdir)

    if creates:
        # do not run the command if the line contains creates=filename
        # and the filename already exists.  This allows idempotence
        # of command executions.
        if glob.glob(creates):
            module.exit_json(
                cmd=args,
                stdout="skipped, since %s exists" % creates,
                changed=False,
                rc=0
            )

    if removes:
        # do not run the command if the line contains removes=filename
        # and the filename does not exist.  This allows idempotence
        # of command executions.
        if not glob.glob(removes):
            module.exit_json(
                cmd=args,
                stdout="skipped, since %s does not exist" % removes,
                changed=False,
                rc=0
            )

    if warn:
        check_command(module, args)

    startd = datetime.datetime.now()

    if not module.check_mode:
        rc, out, err = module.run_command(args, executable=executable, use_unsafe_shell=shell, encoding=None, data=stdin)
    elif creates or removes:
        rc = 0
        out = err = b'Command would have run if not in check mode'
    else:
        module.exit_json(msg="skipped, running in check mode", skipped=True)

    endd = datetime.datetime.now()
    delta = endd - startd

    result = dict(
        cmd=args,
        stdout=out.rstrip(b"\r\n"),
        stderr=err.rstrip(b"\r\n"),
        rc=rc,
        start=str(startd),
        end=str(endd),
        delta=str(delta),
        changed=True,
    )

    if rc != 0:
        module.fail_json(msg='non-zero return code', **result)

    module.exit_json(**result)


if __name__ == '__main__':
    main()
