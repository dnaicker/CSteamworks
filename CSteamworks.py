#!/usr/bin/env python
#  Created by Riley Labrecque for Shorebound Studios
#  This script requires Python 3.3+
#  This script is licensed under the MIT License
#  See the included LICENSE.txt
#  or the following for more info
#  http://www.tldrlegal.com/license/mit-license

from __future__ import print_function

import os

CPP_HEADER = """
// This file is automatically generated!

#include "steam_gameserver.h" // Includes steam_api internally

#if defined( _WIN32 )
#define SB_API extern "C"  __declspec( dllexport )
#elif defined( GNUC )
#define SB_API extern "C" __attribute__ ((visibility ("default")))
#else
#define SB_API extern "C"
#endif

// A few functions return CSteamID which can not be done when using extern "C"
// We could slam it directly to uint64, but that doesn't give other wrappers the info they require.
typedef uint64 SteamID_t;
"""[1:]

g_files = [f for f in os.listdir('steam') if os.path.isfile(os.path.join('steam', f))]

# We don't currently support the following intefaces because they don't provide a factory of their own.
# You are expected to call GetISteamGeneric to get them. That's a little too much for this script at this point.
# They are extremely small and rarely used interfaces, It might just be better to do it manually for them.
if 'isteamappticket.h' in g_files:
    g_files.remove('isteamappticket.h')
if 'isteamgamecoordinator.h' in g_files:
    g_files.remove('isteamgamecoordinator.h')

try:
    os.makedirs('wrapper/')
except OSError:
    pass

g_methodnames = []

for filename in g_files:
    print('Opening: "' + filename + '"')
    with open('steam/' + filename, 'r') as f:
        output = []
        depth = 0
        iface = None
        ifacedepth = 0
        bInMultiLineCommentDepth = False
        bDisableCode = False
        for linenum, line in enumerate(f):
            linenum += 1
            bMultiLineCommentCodeOnThisLine = False

            line = line.split('//', 1)[0].strip()
            if len(line) == 0:
                continue

            pos = line.find('/*')
            if pos != -1:
                bInMultiLineCommentDepth = True
                endpos = line.find('*/')
                if endpos != -1:
                    bInMultiLineCommentDepth = False
                else:
                    line = line.split('/*', 1)[0].strip()
                    if len(line) == 0:
                        continue
                    else:
                        bMultiLineCommentCodeOnThisLine = True

            pos = line.find('*/')
            if pos != -1:
                bInMultiLineCommentDepth = False

                line = line[pos+len('*/'):].strip()
                if len(line) == 0:
                    continue

            if bInMultiLineCommentDepth and not bMultiLineCommentCodeOnThisLine:
                continue

            pos = line.find('class ISteam')
            if pos != -1:
                if line.find(';') != -1:
                    continue
                iface = line[pos + len('class '):].split()[0]
                ifacedepth = depth
                print(iface)

                if iface.startswith('ISteamPS3OverlayRender'):
                    bDisableCode = True
                    output.append('#if _PS3')
                elif 'Response' in line:  # We don't have a proper way to call responses yet
                    bDisableCode = True
                    output.append('#if 0 // Disable Reponses')

            if iface:
                if line.startswith('#'):
                    output.append(line.strip() + '')
                elif line.find('virtual') != -1 and line.find(' = 0;') != -1:
                    splitline = line[len('virtual '):].split()
                    state = 0
                    returnvalue = ''
                    methodname = ''
                    realmethodname = ''
                    args = ''
                    for token in splitline:
                        if not token:
                            continue

                        if state == 0:  # Return Value
                            if token.startswith('*'):
                                returnvalue += '*'
                                state = 1
                            elif token.find('(') == -1:
                                returnvalue += token + ' '
                            else:
                                state = 1

                        if state == 1:  # Method Name
                            if token.startswith('*'):
                                token = token[1:]
                            realmethodname = token.split('(', 1)[0]
                            methodname = iface + '_' + realmethodname

                            if methodname in g_methodnames:
                                methodname += '_'
                            g_methodnames.append(methodname)

                            if token[-1] == ')':
                                state = 3
                            elif token[-1] != '(':  # Edge case in GetAvailableVoice
                                token = token.split('(')[1]
                                state = 2
                            else:
                                state = 2
                                continue

                        if state == 2:  # Args
                            if token.startswith(')'):
                                state = 3
                            elif token.endswith(')'):  # Edge case in SetGameData and GetAvailableVoice
                                args += token[:-1]
                                state = 3
                            elif token.strip() == '*,':  # Edge case in GetClanChatMessage
                                args += '*peChatEntryType, '
                            elif token.strip() == '*':  # Edge case in GetClanChatMessage
                                args += '*pSteamIDChatter '
                            else:
                                args += token + ' '

                        if state == 3:  # ) = 0;
                            continue

                    args = args.rstrip()
                    typelessargs = ''
                    if args != '':
                        argssplitted = args.strip().split(' ')
                        for i, token in enumerate(argssplitted):
                            if token == '=' or token == '""':  # Handle defaulted arguments
                                continue
                            if token == '0':  # Like f( nChannel = 0 )
                                token = argssplitted[i - 2]

                            if token.startswith('**'):
                                typelessargs += token[2:] + ' '
                            elif token.startswith('*'):
                                typelessargs += token[1:] + ' '
                            elif token[-1] == ',':
                                typelessargs += token + ' '
                            elif i == len(argssplitted) - 1:
                                typelessargs += token
                    typelessargs = typelessargs.rstrip()

                    bReturnsCSteamID = False
                    if returnvalue.strip() == 'CSteamID':  # Can not return a class with C ABI
                        bReturnsCSteamID = True
                        returnvalue = 'SteamID_t '  # This actually causes an issue when trying to create a wrapper for the wrapper

                    output.append('SB_API ' + returnvalue + methodname + '(' + args + ') {')
                    if returnvalue.strip() == 'void':
                        output.append('\t' + iface[1:] + '()->' + realmethodname + '(' + typelessargs + ');')
                    elif bReturnsCSteamID:
                        output.append('\treturn ' + iface[1:] + '()->' + realmethodname + '(' + typelessargs + ').ConvertToUint64();')
                    else:
                        output.append('\treturn ' + iface[1:] + '()->' + realmethodname + '(' + typelessargs + ');')
                    output.append('}')
                    output.append('')

            if line.find('{') != -1:
                depth += 1
            if line.find('}') != -1:
                depth -= 1
                if iface and depth == ifacedepth:
                    iface = None
                if bDisableCode:
                    output.append('#endif')
                    bDisableCode = False

        if output:
            with open('wrapper/' + os.path.splitext(filename)[0] + '.cpp', 'w') as out:
                print(CPP_HEADER, file=out)
                for line in output:
                    print(line, file=out)
