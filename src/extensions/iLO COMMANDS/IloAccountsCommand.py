###
# Copyright 2020 Hewlett Packard Enterprise, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
###

# -*- coding: utf-8 -*-
""" Add Account Command for rdmc """

import os
import sys
import json
import getpass

from argparse import ArgumentParser, Action, SUPPRESS, RawDescriptionHelpFormatter

from redfish.ris.ris import SessionExpired
from redfish.ris.rmc_helper import IdTokenError

from rdmc_base_classes import RdmcCommandBase, add_login_arguments_group, login_select_validation, \
                                logout_routine
from rdmc_helper import ReturnCodes, InvalidCommandLineError, ResourceExists, \
                InvalidCommandLineErrorOPTS, NoContentsFoundForOperationError, \
                IncompatibleiLOVersionError, Encryption, InvalidFileInputError

class _AccountParse(Action):
    def __init__(self, option_strings, dest, nargs, **kwargs):
        super(_AccountParse, self).__init__(option_strings, dest, nargs, **kwargs)
    def __call__(self, parser, namespace, values, option_strings):
        """ Account privileges option helper"""

        privkey = {1: 'LoginPriv', 2: 'RemoteConsolePriv', 3:'UserConfigPriv', 4:'iLOConfigPriv', \
         5: 'VirtualMediaPriv', 6: 'VirtualPowerAndResetPriv', 7: 'HostNICConfigPriv', \
         8: 'HostBIOSConfigPriv', 9: 'HostStorageConfigPriv', 10: 'SystemRecoveryConfigPriv'}

        for priv in next(iter(values)).split(','):
            try:
                priv = int(priv)
            except ValueError:
                try:
                    parser.error("Invalid privilege entered: %s. Privileges must " \
                                           "be numbers." % priv)
                except:
                    raise InvalidCommandLineErrorOPTS("")
            try:
                if not isinstance(namespace.optprivs, list):
                    namespace.optprivs = list()
                if option_strings.startswith('--add'):
                    namespace.optprivs.append({privkey[priv]: True})
                elif option_strings.startswith('--remove'):
                    namespace.optprivs.append({privkey[priv]: False})
            except KeyError:
                try:
                    parser.error("Invalid privilege entered: %s. Number does not " \
                                           "match an available privilege." % priv)
                except:
                    raise InvalidCommandLineErrorOPTS("")
    #account_parse.counter = 0

class IloAccountsCommand(RdmcCommandBase):

    """ command to manipulate/add ilo user accounts """
    def __init__(self, rdmcObj):
        RdmcCommandBase.__init__(self,\
            name='iloaccounts',
            usage=None,\
            description='\tView, Add, Remove, and Modify iLO accounts based on the '\
            '\n\tsub-command used.\n\n\tTo view help on specific sub-commands run: '\
            '\n\n\tiloaccounts <sub-command> -h\n\n\t'\
            'Example: iloaccounts add -h\n\n\t*Note*: UserName and LoginName are reversed '\
            '\n\tin the iLO GUI for Redfish compatibility.',
            summary='Views/Adds/deletes/modifies an iLO account on the currently logged in server.',
            aliases=['iloaccount'])
        self.definearguments(self.parser)
        self._rdmc = rdmcObj
        self.typepath = rdmcObj.app.typepath

    def run(self, line):
        """ Main iloaccounts function

        :param line: string of arguments passed in
        :type line: str.
        """
        acct = mod_acct = None
        try:
            (options, args) = self._parse_arglist(line, default=True)
        except (InvalidCommandLineErrorOPTS, SystemExit):
            if ("-h" in line) or ("--help" in line):
                return ReturnCodes.SUCCESS
            else:
                raise InvalidCommandLineErrorOPTS("")

        self.iloaccountsvalidation(options)

        redfish = self._rdmc.app.monolith.is_redfish
        path = self.typepath.defs.accountspath
        results = self._rdmc.app.get_handler(path, service=True, silent=True).dict

        if redfish:
            results = results['Members']
        else:
            results = results['links']['Member']

        for indx, acct in enumerate(results):
            acct = self._rdmc.app.get_handler(acct[self.typepath.defs.hrefstring],\
                                                                service=True, silent=True).dict
            try:
                if hasattr(options, 'identifier'):
                    if acct['Id'] in options.identifier or acct['UserName'] in options.identifier:
                        if redfish:
                            path = acct['@odata.id']
                        else:
                            path = acct['links']['self']['href']
                        mod_acct = acct
                elif options.command == 'default':
                    results[indx] = acct
                else:
                    raise KeyError
            except KeyError:
                continue
            else:
                if mod_acct:
                    acct = mod_acct
                    break

        if not results:
            raise NoContentsFoundForOperationError("0 iLO Management Accounts were found.")

        outdict = dict()
        if options.command.lower() == 'default':
            if not options.json:
                sys.stdout.write("iLO Account info: \n[Id] UserName (LoginName): "\
                                "\nPrivileges\n-----------------\n")
            for acct in sorted(results, key=lambda k: int(k['Id'])):
                privstr = ""
                privs = acct['Oem'][self.typepath.defs.oemhp]['Privileges']

                if 'ServiceAccount' in list(acct['Oem'][self.typepath.defs.oemhp].keys()) and \
                acct['Oem'][self.typepath.defs.oemhp]['ServiceAccount']:
                    service = 'ServiceAccount=True'
                else:
                    service = 'ServiceAccount=False'
                if not options.json:
                    for priv in privs:
                        privstr += priv + '=' + str(privs[priv]) + '\n'
                    sys.stdout.write("[%s] %s (%s):\n%s\n%s\n" % (acct['Id'], acct['UserName'], \
                            acct['Oem'][self.typepath.defs.oemhp]['LoginName'], service, privstr))
                keyval = '['+str(acct['Id'])+'] '+acct['UserName']
                outdict[keyval] = privs
                outdict[keyval]['ServiceAccount'] = service.split('=')[-1].lower()
            if options.json:
                sys.stdout.write(str(json.dumps(outdict, indent=2, sort_keys=True)))
                sys.stdout.write('\n')
        elif options.command.lower() == 'changepass':
            if not acct:
                raise InvalidCommandLineError("Unable to find the specified account.")
            if not options.acct_password:
                sys.stdout.write('Please input the new password.\n')
                tempinput = getpass.getpass()
                self.credentialsvalidation('', '', tempinput, '', True, options)
                options.acct_password = tempinput
            account = options.identifier.lower()
            self.credentialsvalidation('', '', options.acct_password.split('\r')[0], '', True)
            body = {'Password': options.acct_password.split('\r')[0]}

            if path and body:
                self._rdmc.app.patch_handler(path, body)
            else:
                raise NoContentsFoundForOperationError('Unable to find the specified account.')

        elif options.command.lower() == 'add':
            if options.encode:
                args[2] = Encryption.decode_credentials(args[2])

            privs = self.getprivs(options)
            path = self.typepath.defs.accountspath

            body = {"UserName": options.identifier, "Password": options.acct_password, "Oem": \
                    {self.typepath.defs.oemhp: {"LoginName": options.loginname}}}
            if privs:
                body["Oem"][self.typepath.defs.oemhp].update({"Privileges": privs})
            self.credentialsvalidation(options.identifier, options.loginname, \
                                       options.acct_password, acct, True)
            if options.serviceacc:
                body["Oem"][self.typepath.defs.oemhp].update({"ServiceAccount": True})
            if options.role:
                if self._rdmc.app.getiloversion() >= 5.140:
                    body["RoleId"] = options.role
                else:
                    raise IncompatibleiLOVersionError("Roles can only be set in iLO 5"\
                                                                                " 1.40 or greater.")
            if path and body:
                self._rdmc.app.post_handler(path, body)
        elif options.command.lower() == 'modify':
            if not mod_acct:
                raise InvalidCommandLineError("Unable to find the specified account.")
            body = {}

            if options.optprivs:
                body.update({'Oem': {self.typepath.defs.oemhp: {'Privileges': {}}}})
                if any(priv for priv in options.optprivs if 'SystemRecoveryConfigPriv' in priv) \
                                                            and 'SystemRecoveryConfigPriv' not in \
                                                                        self.getsesprivs().keys():
                    raise IdTokenError("The currently logged in account must have The System "\
                                         "Recovery Config privilege to add the System Recovery "\
                                         "Config privilege.")
                privs = self.getprivs(options)
                body['Oem'][self.typepath.defs.oemhp]['Privileges'] = privs

            if options.role and self._rdmc.app.getiloversion >= 5.140:
                body["RoleId"] = options.role

            self._rdmc.app.patch_handler(path, body)

        elif options.command.lower() == 'delete':
            if not acct:
                raise InvalidCommandLineError("Unable to find the specified account.")
            self._rdmc.app.delete_handler(path)

        elif 'cert' in options.command.lower():
            certpath = '/redfish/v1/AccountService/UserCertificateMapping/'
            privs = self.getsesprivs()
            if self.typepath.defs.isgen9:
                IncompatibleiLOVersionError("This operation is only available on gen 10 "\
                                                  "and newer machines.")
            elif privs['UserConfigPriv'] == False:
                raise IdTokenError("The currently logged in account must have The User "\
                                     "Config privilege to manage certificates for users.")
            else:
                if options.command.lower() == 'addcert':
                    if not acct:
                        raise InvalidCommandLineError("Unable to find the specified account.")
                    body = {}
                    username = acct['UserName']
                    account = acct['Id']
                    fingerprintfile = options.certificate
                    if os.path.exists(fingerprintfile):
                        with open(fingerprintfile, 'r') as fingerfile:
                            fingerprint = fingerfile.read()
                    else:
                        raise InvalidFileInputError('%s cannot be read.' % fingerprintfile)
                    body = {"Fingerprint": fingerprint, "UserName": username}
                    self._rdmc.app.post_handler(certpath, body)

                elif options.command.lower() == 'deletecert':
                    if not acct:
                        raise InvalidCommandLineError("Unable to find the specified account.")
                    certpath += acct['Id']
                    self._rdmc.app.delete_handler(certpath)

        else:
            raise InvalidCommandLineError('Invalid command.')

        logout_routine(self, options)
        #Return code
        return ReturnCodes.SUCCESS

    def getprivs(self, options):
        """ find and return the privileges to set

        :param options: command line options
        :type options: list.
        """
        sesprivs = self.getsesprivs()
        setprivs = {}
        availableprivs = self.getsesprivs(availableprivsopts=True)

        if not 'UserConfigPriv' in sesprivs.keys():
                raise IdTokenError("The currently logged in account does not have the User Config "\
                                 "privilege and cannot add or modify user accounts.")

        if options.optprivs:
            for priv in options.optprivs:
                priv = next(iter(priv.keys()))
                if priv not in availableprivs:
                    raise IncompatibleiLOVersionError("Privilege %s is not available on this "\
                                                                            "iLO version." % priv)

            if all(priv.values()[0] for priv in options.optprivs):
                if any(priv for priv in options.optprivs if 'SystemRecoveryConfigPriv' in priv) and\
                                            'SystemRecoveryConfigPriv' not in sesprivs.keys():
                    raise IdTokenError("The currently logged in account must have The System "\
                                     "Recovery Config privilege to add the System Recovery "\
                                     "Config privilege.")
                else:
                    setprivs = {}
            for priv in options.optprivs:
                setprivs.update(priv)

        return setprivs

    def getsesprivs(self, availableprivsopts=False):
        """Finds and returns the curent session's privileges

        :param availableprivsopts: return available privileges
        :type availableprivsopts: boolean.
        """
        if self._rdmc.app.current_client:
            sespath = self._rdmc.app.current_client.session_location
            sespath = self._rdmc.app.current_client.default_prefix + \
                                sespath.split(self._rdmc.app.current_client.\
                                              default_prefix)[-1]

            ses = self._rdmc.app.get_handler(sespath, service=False, silent=True)

            if not ses:
                raise SessionExpired("Invalid session. Please logout and "\
                                    "log back in or include credentials.")

            sesprivs = ses.dict['Oem'][self.typepath.defs.oemhp]['Privileges']
            availableprivs = ses.dict['Oem'][self.typepath.defs.oemhp]['Privileges'].keys()
            for priv, val in sesprivs.items():
                if not val:
                    del sesprivs[priv]
        else:
            sesprivs = None
        if availableprivsopts:
            return availableprivs
        else:
            return sesprivs

    def credentialsvalidation(self, username='', loginname='', password='', acct=None, \
                                                            check_password=False, options=None):
        """ sanity validation of credentials
        :param username: username to be added
        :type username: str.
        :param loginname: loginname to be added
        :type loginname: str.
        :param password: password to be added
        :type password: str.
        :param accounts: target federation account
        :type accounts: dict.
        :param check_password: flag to check password
        :type check_password: bool.
        """
        username_max_chars = 39 #60
        loginname_max_chars = 39 #60
        password_max_chars = 39 #PASSWORD MAX CHARS
        password_min_chars = 8  #PASSWORD MIN CHARS

        password_min_chars = next(iter(self._rdmc.app.select(\
                'AccountService.'))).dict['Oem'][self.typepath.defs.oemhp]['MinPasswordLength']

        if username != '' and loginname != '':
            if len(username) > username_max_chars:
                raise InvalidCommandLineError('Username exceeds maximum length'\
                    '. Use at most %s characters.' % username_max_chars)

            if len(loginname) > loginname_max_chars:
                raise InvalidCommandLineError('Login name exceeds maximum '\
                    'length. Use at most %s characters.' % loginname_max_chars)

            try:
                if acct['UserName'] == username or acct['Oem'][self.typepath.defs.oemhp]\
                                                                    ['LoginName'] == loginname:
                    raise ResourceExists('Username or login name is already in use.')
            except KeyError:
                pass

        if check_password:
            if password == '' or password == '/r':
                raise InvalidCommandLineError('An invalid password was entered.')
            else:
                if len(password) > password_max_chars:
                    raise InvalidCommandLineError('Password length is invalid.'\
                            ' Use at most %s characters.' % password_max_chars)
                if len(password) < password_min_chars:
                    raise InvalidCommandLineError('Password length is invalid.'\
                            ' Use at least %s characters.' % password_min_chars)

    def iloaccountsvalidation(self, options):
        """ add account validation function

        :param options: command line options
        :type options: list.
        """
        login_select_validation(self, options)

    @staticmethod
    def options_argument_group(parser):
        """ Define optional arguments group

        :param parser: The parser to add the --addprivs option group to
        :type parser: ArgumentParser/OptionParser
        """
        group = parser.add_argument_group('GLOBAL OPTIONS', 'Options are available for all ' \
                                                'arguments within the scope of this command.')

        group.add_argument(
            '--addprivs',
            dest='optprivs',
            nargs='*',
            action=_AccountParse,
            type=str,
            help="Optionally include this flag if you wish to specify "\
            "which privileges you want added to the iLO account. Pick "\
            'privileges from the privilege list in above help text. EX: --addprivs=1,2,4',
            default=None,
            metavar='Priv,'
        )

    def definearguments(self, customparser):
        """ Wrapper function for new command main function

        :param customparser: command line input
        :type customparser: parser.
        """
        if not customparser:
            return

        add_login_arguments_group(customparser)
        customparser.add_argument(
            '-j',
            '--json',
            dest='json',
            action="store_true",
            help="Optionally include this flag if you wish to change the"\
            " displayed output to JSON format. Preserving the JSON data"\
            " structure makes the information easier to parse.",
            default=False
        )
        subcommand_parser = customparser.add_subparsers(dest='command')
        privilege_help='\n\n\tPRIVILEGES:\n\t1: Login\n\t2: Remote Console\n\t3: User Config\n\t4:'\
            ' iLO Config\n\t5: Virtual Media\n\t6: Virtual Power and Reset\n\n\tiLO 5 added '\
            'privileges:\n\t7: Host NIC Config\n\t8: Host Bios Config\n\t9: Host Storage Config'\
            '\n\t10: System Recovery Config'
        #default sub-parser
        default_parser = subcommand_parser.add_parser(
            'default',
            help='Running without any sub-command will return all account information on the '\
            'currently logged in server.'
        )
        add_login_arguments_group(default_parser)
        #add sub-parser
        add_help='\tAdds an iLO user account to the currently logged in server with privileges\n\t'\
            'specified in --addprivs.'
        add_parser = subcommand_parser.add_parser(
            'add',
            help=add_help,
            description=add_help+'\n\t*Note*:By default only the login privilege is added to the'\
            ' newly created account\n\twith role "ReadOnly"in iLO 5 and no privileges in iLO 4.'\
            +privilege_help+
            '\n\n\tExamples:\n\n\tAdd an account with specific privileges:\n\t\tiloaccounts add '\
            'username accountname password --addprivs 1,2,4\n\n\tAdd an account and specify '\
            'privileges by role:\n\t\tiloaccounts add username accountname password --role '\
            'ReadOnly',
            formatter_class=RawDescriptionHelpFormatter
        )
        #addprivs
        add_parser.add_argument(
            'identifier',
            help='The username or ID of the iLO account to modify.',
            metavar='USERNAMEorID#'
        )
        add_parser.add_argument(
            'loginname',
            help='The loginname of the iLO account to add. This is NOT used to login to the newly '\
            'created account.',
            metavar='LOGINNAME'
        )
        add_parser.add_argument(
            'acct_password',
            help='The password of the iLO account to add. If you do not include a password, you '\
            'will be prompted to enter one before an account is created. This is used to login to '\
            'the newly created account.',
            metavar='PASSWORD',
            nargs='?',
            default=''
        )
        add_parser.add_argument(
            '--role',
            dest='role',
            choices=['Administrator', 'ReadOnly', 'Operator'],
            help="Optionally include this option if you would like to specify Privileges by role."\
            " Roles are a set of privileges created based on the role of the account.",
            default=None
        )
        add_parser.add_argument(
            '--serviceaccount',
            dest='serviceacc',
            action="store_true",
            help="Optionally include this flag if you wish to created account "\
            "to be a service account.",
            default=False
        )
        add_login_arguments_group(add_parser)
        self.options_argument_group(add_parser)
        #modify sub-parser
        modify_help='\tModifies the provided iLO user account on the currently logged in server'\
            '\n\tadding privileges using "--addprivs" to include privileges and using\n\t'\
            '"--removeprivs" for removing privileges.'
        modify_parser = subcommand_parser.add_parser(
            'modify',
            help=modify_help,
            description=modify_help+privilege_help+'\n\n\tExamples:\n\n\tModify an iLO account\'s '\
            'privileges by adding:\n\tiloaccounts modify username --addprivs 3,5\n\n\t'
            'Modify an iLO account\'s privileges by removal:\n\tiloaccounts modify username '
            '--removeprivs 10\n\n\tOr modify an iLO account\'s privileges by both simultaneously '\
            'adding and removing privleges:\n\n\tiloaccounts modify username --addprivs 3,7 '\
            '--removeprivs 9,10',
            formatter_class=RawDescriptionHelpFormatter
        )
        modify_parser.add_argument(
            'identifier',
            help='The username or ID of the iLO account to modify.',
            metavar='USERNAMEorID#'
        )
        add_login_arguments_group(modify_parser)
        self.options_argument_group(modify_parser) #addprivs
        modify_parser.add_argument(
            '--role',
            dest='role',
            choices=['Administrator', 'ReadOnly', 'Operator'],
            help="Optionally include this option if you would like to specify Privileges by role."\
            " Roles are a set of privileges created based on the role of the account.",
            default=None
        )
        modify_parser.add_argument(
            '--removeprivs',
            dest='optprivs',
            nargs='*',
            action=_AccountParse,
            type=str,
            help="Include this flag if you wish to specify "\
            "which privileges you want removed from the iLO account. Pick "\
            "privileges from the privilege list in the above help text. EX: --removeprivs=1,2,4",
            default=None,
            metavar='Priv,'
        )
        #changepass sub-parser
        changepass_help='Changes the password of the provided iLO user account on the currently '\
            'logged in server.'
        changepass_parser = subcommand_parser.add_parser(
            'changepass',
            help=changepass_help,
            description=changepass_help+'\n\nExamples:\n\nChange the password of an account:\n\t'\
            'iloaccounts changepass 2 newpassword',
            formatter_class=RawDescriptionHelpFormatter
        )
        changepass_parser.add_argument(
            'identifier',
            help='The username or ID of the iLO account to change the password for.',
            metavar='USERNAMEorID#'
        )
        changepass_parser.add_argument(
            'acct_password',
            help='The password to change the selected iLO account to. If you do not include a '\
            'password, you will be prompted to enter one before an account is created. This is '\
            'used to login to the newly created account.',
            metavar='PASSWORD',
            nargs='?',
            default=''
        )
        add_login_arguments_group(changepass_parser)
        #delete sub-parser
        delete_help='Deletes the provided iLO user account on the currently logged in server.'
        delete_parser = subcommand_parser.add_parser(
            'delete',
            help=delete_help,
            description=delete_help+'\n\nExamples:\n\nDelete an iLO account:\n\t'\
            'iloaccounts delete username',
            formatter_class=RawDescriptionHelpFormatter
        )
        delete_parser.add_argument(
            'identifier',
            help='The username or ID of the iLO account to delete.',
            metavar='USERNAMEorID#'
        )
        add_login_arguments_group(delete_parser)
        #addcert sub-parser
        addcert_help='Adds a certificate to the provided iLO user account on the currently logged'\
            ' in server.'
        addcert_parser = subcommand_parser.add_parser(
            'addcert',
            help=addcert_help,
            description=addcert_help+'\n\nExamples:\n\nAdd a user certificate to the provided '\
            'iLO account.\n\t'
            'iloaccounts addcert accountUserName C:\Users\user\cert.txt',
            formatter_class=RawDescriptionHelpFormatter
        )
        addcert_parser.add_argument(
            'identifier',
            help='The username or ID of the iLO account to add a certificate to.',
            metavar='USERNAMEorID#'
        )
        addcert_parser.add_argument(
            'certificate',
            help='The certificate to add to the provided iLO account.',
            metavar='X.509CERTIFICATE'
        )
        #deletecert sub-parser
        deletecert_help='Deletes a certificate to the provided iLO user account on the currently '\
        'logged in server.'
        deletecert_parser = subcommand_parser.add_parser(
            'deletecert',
            help=deletecert_help,
            description=deletecert_help+'\n\nExamples:\n\nDelete a user certificate from the '\
            'provided iLO account.\n\tiloaccounts deletecert username',
            formatter_class=RawDescriptionHelpFormatter
        )
        deletecert_parser.add_argument(
            'identifier',
            help='The username or ID of the iLO account to delete the certificate from.',
            metavar='USERNAMEorID#'
        )
