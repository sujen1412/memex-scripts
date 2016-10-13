# This code converts an html file named by its url to CCA format in CBOR

import os
import sys
import cbor
from tika import parser
import getopt
from urlparse import urlparse
import hashlib
import json
from multiprocessing import Pool

_helpMessage = '''

Usage: html_cca_converter [<cca dir> [<urlDomain>] [outputDir]]

Operation:
-d --dataDir
    The directory where CCA CBOR JSON files are located.
-u --url
    The URL to be appended to filenames to get exact urls.
-o --outputDir
	The path to an outputDir where the CCA documents will be stored 
'''

global urlDomain
global outputDir

class _Usage(Exception):
    '''An error for problems with arguments on the command line.'''

    def __init__(self, msg):
        self.msg = msg


def list_files(dir):
    r = []
    subdirs = [x[0] for x in os.walk(dir)]
    for subdir in subdirs:
        files = os.walk(subdir).next()[2]
        if (len(files) > 0):
            for file in files:
                r.append(subdir + "/" + file)
    return r


def getKey(url, creationTime):
    stringToHash = url + "-" + str(creationTime)
    hashed = hashlib.sha256()
    hashed.update(stringToHash)
    urlSHAHex = hashed.hexdigest()
    key = urlSHAHex.upper()
    return key


def getContentType():
    contentType = 'text/html'
    return contentType


def getFileContents(file):
    f = open(file, "r")
    content = f.read()
    content = "<html><head></head><body> " + content + "</body></html>"
    f.close()
    return content


def writeToOutput(ccaDoc, outputDir):
    if not os.path.exists(outputDir):
        os.makedirs(outputDir)
        print(outputDir)
    outputPath = outputDir + "/" + ccaDoc["key"]
    f = open(outputPath, "w")
    f.write(cbor.dumps(json.dumps(ccaDoc)))
    f.close()


def getCCA(file, urlDomain):
    creationTime = int(os.stat(file).st_atime)
    url = urlDomain + os.path.basename(file)
    # print("Processing file : " + url)
    imported = creationTime
    response = {}
    response["body"] = getFileContents(file)
    response["headers"] = {}
    response["headers"]["Content-Type"] = getContentType()
    key = getKey(url, creationTime)
    ccaDoc = {}
    ccaDoc["url"] = url
    ccaDoc["imported"] = imported
    ccaDoc["response"] = response
    ccaDoc["key"] = key
    return ccaDoc


def convertFileToCCA(file):
    global urlDomain
    global outputDir
    ccaDoc = getCCA(file, urlDomain)
    writeToOutput(ccaDoc, outputDir)
    print ("Converted " + str(file) + " to " + ccaDoc["key"])


def convertToCCA(dataDir, urlDomain, outputDir):
    htmlFileList = list_files(dataDir)
    pool = Pool(3)
    results = pool.map(convertFileToCCA, htmlFileList)
    pool.close()
    pool.join()
    # for file in htmlFileList:
    #     # creationTime = int(os.stat(file).st_atime)
    #     # url = urlDomain + os.path.basename(file)
    #     # print("Processing file : " + url)
    #     # imported = creationTime
    #     # response = {}
    #     # response["body"] = getFileContents(file)
    #     # response["headers"] = {}
    #     # response["headers"]["Content-Type"] = getContentType()
    #     # key = getKey(url)
    #     # ccaDoc = {}
    #     # ccaDoc["url"] = url
    #     # ccaDoc["imported"] = imported
    #     # ccaDoc["response"] = response
    #     # ccaDoc["key"] = key
    #     ccaDoc = getCCA(file, urlDomain)
        # writeToOutput(ccaDoc, outputDir)
        # counter += 1
    # print(response["body"])
    print("Converted documents")


def main(argv=None):
    if argv is None:
        argv = sys.argv
    global urlDomain
    global outputDir
    try:
        try:
            opts, args = getopt.getopt(argv[1:], 'hv:d:u:o:', ['help', 'verbose', 'dataDir=', 'url=', 'outputDir='])
        except getopt.error, msg:
            raise _Usage(msg)

        if len(opts) == 0:
            raise _Usage(_helpMessage)
        team = None
        crawlerId = None
        dataDir = None
        url = None
        index = None

        for option, value in opts:
            if option in ('-h', '--help'):
                raise _Usage(_helpMessage)
            elif option in ('-v', '--verbose'):
                global _verbose
                _verbose = True
            elif option in ('-d', '--dataDir'):
                dataDir = value
            elif option in ('-u', '--url'):
                url = value
            elif option in ('-o', '--outputDir'):
                outputDir = value

        if dataDir == None or url == None or outputDir == None:
            raise _Usage(_helpMessage)
        urlDomain = url

        convertToCCA(dataDir, url, outputDir)

    except _Usage, err:
        print >> sys.stderr, sys.argv[0].split('/')[-1] + ': ' + str(err.msg)
        return 2


if __name__ == "__main__":
    sys.exit(main())
