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
""" RawPatch Command for rdmc """

import os
import re
import sys
import json

from collections import OrderedDict

from argparse import ArgumentParser

from rdmc_base_classes import RdmcCommandBase, add_login_arguments_group, login_select_validation, \
                                logout_routine
from rdmc_helper import ReturnCodes, InvalidCommandLineError, InvalidFileFormattingError, \
                    InvalidCommandLineErrorOPTS, InvalidFileInputError, Encryption

class RawPatchCommand(RdmcCommandBase):
    """ Raw form of the patch command """
    def __init__(self, rdmcObj):
        RdmcCommandBase.__init__(self,\
            name='rawpatch',\
            usage='rawpatch [FILENAME]\n\n\tRun to send a patch from the data' \
                    ' in the input file.\n\tMultiple PATCHes can be performed in sequence by '\
                    '\n\tadding more path/body key/value pairs.\n'
                    '\n\texample: rawpatch rawpatch.txt' \
                    '\n\n\tExample input file:\n\t{\n\t    "/redfish/' \
                    'v1/systems/(system ID)":\n\t    {\n\t        ' \
                    '"AssetTag": "NewAssetTag"\n\t    }\n\t}',\
            summary='Raw form of the PATCH command.',\
            aliases=['rawpatch'],\
            argparser=ArgumentParser())
        self.definearguments(self.parser)
        self._rdmc = rdmcObj

    def run(self, line):
        """ Main raw patch worker function

        :param line: command line input
        :type line: string.
        """
        try:
            (options, _) = self._parse_arglist(line)
        except (InvalidCommandLineErrorOPTS, SystemExit):
            if ("-h" in line) or ("--help" in line):
                return ReturnCodes.SUCCESS
            else:
                raise InvalidCommandLineErrorOPTS("")

        headers = {}
        results = []

        self.patchvalidation(options)

        contentsholder = None
        try:
            with open(options.path, 'r') as _if:
                contentsholder = json.loads(_if.read(), object_pairs_hook=OrderedDict)
        except IOError:
            raise InvalidFileInputError("File '%s' doesn't exist. " \
                                "Please create file by running 'save' command." % options.path)
        except (ValueError):
            raise InvalidFileFormattingError("Input file '%s' was not " \
                                                            "formatted properly." % options.path)

        if options.headers:
            extraheaders = options.headers.split(',')

            for item in extraheaders:
                header = item.split(':')

                try:
                    headers[header[0]] = header[1]
                except:
                    raise InvalidCommandLineError("Invalid format for --headers option.")

        if "path" in contentsholder and "body" in contentsholder:
            results.append(self._rdmc.app.patch_handler(contentsholder["path"], \
                  contentsholder["body"], headers=headers, silent=options.silent, \
                  optionalpassword=options.biospassword, service=options.service))

        elif all([re.match("^\/(\S+\/?)+$", key) for key in contentsholder]):
            for path, body in contentsholder.items():
                results.append(self._rdmc.app.patch_handler(path, \
                                body, headers=headers, silent=options.silent, \
                                optionalpassword=options.biospassword, service=options.service))

        else:
            raise InvalidFileFormattingError("Input file '%s' was not format properly." % \
                                                                                    options.path)

        returnresponse = False

        if options.response or options.getheaders:
            returnresponse = True

        if results and returnresponse:
            for result in results:
                if options.getheaders:
                    sys.stdout.write(json.dumps(dict(result.getheaders())) + "\n")

                if options.response:
                    sys.stdout.write(result.read)
                    sys.stdout.write("\n")

        logout_routine(self, options)
        #Return code
        return ReturnCodes.SUCCESS

    def patchvalidation(self, options):
        """ Raw patch validation function

        :param options: command line options
        :type options: list.
        """
        login_select_validation(self, options, skipbuild=True)

    def definearguments(self, customparser):
        """ Wrapper function for new command main function

        :param customparser: command line input
        :type customparser: parser.
        """
        if not customparser:
            return

        add_login_arguments_group(customparser)

        customparser.add_argument(
            'path',
            help="Path to the JSON file containing the data to be patched.",
        )
        customparser.add_argument(
            '--silent',
            dest='silent',
            action="store_true",
            help="""Use this flag to silence responses""",
            default=False,
        )
        customparser.add_argument(
            '--response',
            dest='response',
            action="store_true",
            help="Use this flag to return the iLO response body.",
            default=False
        )
        customparser.add_argument(
            '--getheaders',
            dest='getheaders',
            action="store_true",
            help="Use this flag to return the iLO response headers.",
            default=False
        )
        customparser.add_argument(
            '--headers',
            dest='headers',
            help="Use this flag to add extra headers to the request."\
            "\t\t\t\t\t Usage: --headers=HEADER:VALUE,HEADER:VALUE",
            default=None,
        )
        customparser.add_argument(
            '--service',
            dest='service',
            action="store_true",
            help="""Use this flag to enable service mode and increase the function speed""",
            default=False,
        )
        customparser.add_argument(
            '--biospassword',
            dest='biospassword',
            help="Select this flag to input a BIOS password. Include this"\
            " flag if second-level BIOS authentication is needed for the"\
            " command to execute. This option is only used on Gen 9 systems.",
            default=None,
        )
