# This code converts an html file named by its url to CCA format in CBOR

import os
import sys
import cbor
from tika import parser
import getopt
from urlparse import urlparse
import hashlib
import json

_helpMessage = '''

Usage: html_cca_converter [<cca dir> [<urlDomain>] [outputDir]]

Operation:
-d --dataDir
    The directory where CCA CBOR JSON files are located.
-u --url
    The URL Domain to be appended to filenames to get exact urls.
-o --outputDir
	The path to an outputDir where the CCA documents will be stored 
'''
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

def getKey(url):
	hostname = urlparse(url).hostname
	hostname = hostname.replace(".","_").split("_")[::-1]
	reverseUrl = ''
	for s in hostname:
		reverseUrl += s +'_'
	hashed = hashlib.sha256()
	hashed.update(url)
	urlSHAHex = hashed.hexdigest()
	key = reverseUrl+urlSHAHex

	return key

def getContentType():
	contentType = 'text/html'
	return contentType

def getFileContents(file):
	f = open(file, "r").read()
	return f

def writeToOutput(ccaDoc, outputDir):
	if not os.path.exists(outputDir):
		os.makedirs(outputDir)
		print(outputDir)
	outputPath = outputDir + "/" + ccaDoc["key"]
	f = open(outputPath,"w")
	f.write(cbor.dumps(json.dumps(ccaDoc)))
	f.close()


def convertToCCA(dataDir, urlDomain, outputDir):
	htmlFileList = list_files(dataDir)
	counter = 0
	for file in htmlFileList:
		creationTime = int(os.stat(file).st_atime)
		url = urlDomain + os.path.basename(file)
		print("Processing file : " + url)
		imported = creationTime
		response = {}
		response["body"] = getFileContents(file)
		response["headers"] = {}
		response["headers"]["Content-Type"] = getContentType()
		key = getKey(url)
		ccaDoc = {}
		ccaDoc["url"] = url
		ccaDoc["imported"] = imported
		ccaDoc["response"] = response
		ccaDoc["key"] = key
		writeToOutput(ccaDoc,outputDir)
		counter += 1
		# print(response["body"])
	print("Converted : " + str(counter) + " documents")

def main(argv=None):
   if argv is None:
     argv = sys.argv


   if(len(argv)<4):
   	 print(_helpMessage)
   	 exit()

   convertToCCA(argv[1], argv[2], argv[3])

if __name__ == "__main__":
   sys.exit(main())
