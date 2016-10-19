#!/usr/bin/env python2.7
# encoding: utf-8
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 
# $Id$
#
# Author: mattmann
# Description: This program reads a Common Crawl Architecture dump 
# directory as generated by Apache Nutch, e.g,. see:
# https://wiki.apache.org/nutch/CommonCrawlDataDumper
# and then uses that CBOR-encoded JSON data as a basis for posting
# the data to Elasticsearch using this simple schema:
#
#
# {
#   url : <url of raw page>,
#   timestamp: <timestamp for data when scraped, in epoch milliseconds>,
#   team: <name of crawling team>,
#   crawler: <name of crawler; each type of crawler should have a distinct name or reference>,
#   raw_content: <full text of raw crawled page>,
#   content_type: <IANA mimetype representing the crawl_data content>,
#   crawl_data {
#     content: <optional; used to store cleaned/processed text, etc>,
#     images:[an array of URIs to the images present within the document],
#     videos:[an array of URIs to the videos present within the document]
# }
# To call this program, do something like the following
# 
#  ./memex_cca_esindex.py -t "JPL" -c "Nutch 1.11-SNAPSHOT" -d crawl_20150410_cca/ \
#   -u https://user:pass@localhost:9200/ -i memex-domains -o stuff \
#   -p dump.json -s http://imagecat.dyndns.org/weapons/alldata/
# 
# If you want verbose logging, turn it on with -v
import codecs
import traceback

from tika import parser
from elasticsearch import Elasticsearch
import json
import os
import cbor
import sys
import getopt
import hashlib
from multiprocessing import Pool
from functools import partial

_verbose = False
_helpMessage = '''

Usage: memex_cca_esindex [-t <crawl team>] [-c <crawler id>] [-d <cca dir> [-u <url>]
        [-i <index>] [-o docType] [-p <path>] [-s <raw store prefix path>]

Operation:
-t --team
    The name of the crawler team, e.g. "JPL"
-c --crawlerId
    The identifier of the crawler, e.g., "Nutch 1.11-SNAPSHOT"
-d --dataDir
    The directory where CCA CBOR JSON files are located.
-u --url
    The URL to Elasticsearch. If you need auth, you can use RFC-1738 to specify the url, e.g., https://user:secret@localhost:443
-p --path
    The path to output file where the data shall be stored instead of indexing to elasticsearch
-s --storeprefix
    The path to raw file store where the raw files are stored. Note that this is different than CBOR file dump.
-i --index
    The Elasticsearch index, e.g., memex-domains, to index to.
-o --docType
    The document type e.g., weapons, to index to.

'''

def list_files(dir):
    r = []
    subdirs = [x[0] for x in os.walk(dir)]
    for subdir in subdirs:
        files = os.walk(subdir).next()[2]
        if (len(files) > 0):
            for file in files:
                r.append(subdir + "/" + file)
    return r


def getContentType(ccaDoc):
    for header in ccaDoc["response"]["headers"]:
        if header[0] == "Content-Type":
            return header[1]
    return "application/octet-stream"

def indexDoc(url, doc, index, docType):
    print "Indexing "+doc["url"]+" to ES at: ["+url+"]"
    es = Elasticsearch([url])
    res = es.index(index=index, doc_type=docType, id=doc["id"], body=doc)
    print(res['created'])

def esIndexDoc(f, team, crawler, index, docType, failedList, failedReasons, procCount,
               url=None, outPath=None, storeprefix=None):
    CDRVersion = 2.0
    outFile = codecs.open(outPath +"/" + str(os.path.basename(f)), 'w', 'utf-8') if outPath else None
    with open(f, 'r') as fd:
            try:
                newDoc = {}
                c = fd.read()
                # fix for no request body out of Nutch CCA
                c.replace("\"body\" : null", "\"body\" : \"null\"")
                ccaDoc = json.loads(cbor.loads(c), encoding='utf8')
                newDoc["url"] = ccaDoc["url"]

                newDoc["timestamp"] = ccaDoc["imported"]
                newDoc["team"] = team
                newDoc["crawler"] = crawler

                contentType = getContentType(ccaDoc)
                newDoc["content_type"] = contentType

                parsed = parser.from_buffer(ccaDoc["response"]["body"].encode("utf-8"))
                newDoc["crawl_data"] = {}
                if "content" in parsed:
                    newDoc["crawl_data"]["content"] = parsed["content"]
                    newDoc["extracted_text"] = parsed["content"]
                if 'inlinks' in ccaDoc and ccaDoc['inlinks']:
                    newDoc["crawl_data"]["obj_parents"] = ccaDoc['inlinks']
                    newDoc["obj_parent"] = ccaDoc['inlinks'][0]
                # CDR version 2.0 additions
                newDoc["id"] = ccaDoc["key"]
                newDoc["obj_original_url"] = ccaDoc["url"]

                if 'text' in contentType or 'ml' in contentType:
                    # web page
                    newDoc["raw_content"] = ccaDoc["response"]["body"]
                else:
                    # binary content, we link to store
                    # ideally we should be storing it both the cases, but the CDR schema decided this way
                    newDoc["obj_stored_url"] = url_to_nutch_dump_path(ccaDoc["url"], prefix=storeprefix)

                newDoc["extracted_metadata"] = parsed["metadata"] if 'metadata' in parsed else {}
                newDoc["version"] = CDRVersion
                verboseLog("Indexing ["+f+"] to Elasticsearch.")
                if url:
                    indexDoc(url, newDoc, index, docType)
                if outFile:
                    outFile.write(json.dumps(newDoc))
                    outFile.write("\n")
                    print "Processed " + f + " successfully"
                procCount += 1
            except Exception as err:
                failedList.append(f)
                failedReasons.append(str(err))
                traceback.print_exc()

def esIndex(ccaDir, team, crawler, index, docType, url=None, outPath=None, storeprefix=None):
    if not url and not outPath:
        raise Exception("Either Elastic Url or output path must be specified.")
    ccaJsonList = list_files(ccaDir)
    print "Processing ["+str(len(ccaJsonList))+"] files."

    procCount = 0
    failedList=[]
    failedReasons=[]
    CDRVersion = 2.0
    # outFile = codecs.open(outPath, 'w', 'utf-8') if outPath else None

    pool = Pool(processes=3)
    results = pool.map(partial(esIndexDoc, team=team, crawler=crawler, index=index,
                               docType=docType, failedList=failedList, failedReasons=failedReasons, procCount=procCount,
                               url=url, outPath=outPath, storeprefix=storeprefix), ccaJsonList)
    pool.close()
    pool.join()

    # for f in ccaJsonList:
    #     with open(f, 'r') as fd:
    #         try:
    #             newDoc = {}
    #             c = fd.read()
    #             # fix for no request body out of Nutch CCA
    #             c.replace("\"body\" : null", "\"body\" : \"null\"")
    #             ccaDoc = json.loads(cbor.loads(c).value, encoding='utf8')
    #             newDoc["url"] = ccaDoc["url"]
    #
    #             newDoc["timestamp"] = ccaDoc["imported"]
    #             newDoc["team"] = team
    #             newDoc["crawler"] = crawler
    #
    #             contentType = getContentType(ccaDoc)
    #             newDoc["content_type"] = contentType
    #
    #             parsed = parser.from_buffer(ccaDoc["response"]["body"].encode("utf-8"))
    #             newDoc["crawl_data"] = {}
    #             if "content" in parsed:
    #                 newDoc["crawl_data"]["content"] = parsed["content"]
    #                 newDoc["extracted_text"] = parsed["content"]
    #             if 'inlinks' in ccaDoc and ccaDoc['inlinks']:
    #                 newDoc["crawl_data"]["obj_parents"] = ccaDoc['inlinks']
    #                 newDoc["obj_parent"] = ccaDoc['inlinks'][0]
    #             # CDR version 2.0 additions
    #             newDoc["_id"] = ccaDoc["key"]
    #             newDoc["obj_original_url"] = ccaDoc["url"]
    #
    #             if 'text' in contentType or 'ml' in contentType:
    #                 # web page
    #                 newDoc["raw_content"] = ccaDoc["response"]["body"]
    #             else:
    #                 # binary content, we link to store
    #                 # ideally we should be storing it both the cases, but the CDR schema decided this way
    #                 newDoc["obj_stored_url"] = url_to_nutch_dump_path(ccaDoc["url"], prefix=storeprefix)
    #
    #             newDoc["extracted_metadata"] = parsed["metadata"] if 'metadata' in parsed else {}
    #             newDoc["version"] = CDRVersion
    #             verboseLog("Indexing ["+f+"] to Elasticsearch.")
    #             if url:
    #                 indexDoc(url, newDoc, index, docType)
    #             if outFile:
    #                 outFile.write(json.dumps(newDoc))
    #                 outFile.write("\n")
    #             procCount += 1
    #         except Exception as err:
    #             failedList.append(f)
    #             failedReasons.append(str(err))
    #             traceback.print_exc()
    # if outFile:
    #     print("Output Stored at %s" % outPath)
    #     outFile.close()
    print "Processed " + str(procCount) + " CBOR files successfully."
    print "Failed files: " + str(len(failedList))

    if _verbose:
        for i in range(len(failedList)):
            verboseLog("File: "+failedList[i]+" failed because "+failedReasons[i])

def verboseLog(message):
    if _verbose:
        print >>sys.stderr, message

class _Usage(Exception):
    '''An error for problems with arguments on the command line.'''
    def __init__(self, msg):
        self.msg = msg

def url_to_nutch_dump_path(url, prefix=None):
    """
    Converts URL to nutch dump path (the regular dump with reverse domain, not the commons crawl dump path)
    :param url: valid url string
    :param prefix: prefix string (default = "")
    :return: nutch dump path prefixed to given path
    """
    domain = url.split("/")[2]
    return "{0}/{1}/{2}".format("" if prefix is None else prefix.strip("/"),
                                "/".join(reversed(domain.split("."))),
                                hashlib.sha256(url).hexdigest().upper())


def main(argv=None):
    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], 'hvt:c:d:u:i:o:p:s:',
                                       ['help', 'verbose', 'team=', 'crawlerId=', 'dataDir=', 'url=', 'index=',
                                        'docType=', 'path=', 'storeprefix='])
        except getopt.error, msg:
            raise _Usage(msg)

        if len(opts) == 0:
            raise _Usage(_helpMessage)
        team=None
        crawlerId=None
        dataDir=None
        url=None
        index=None
        docType=None

        outPath=None
        storePrefix=None

        for option, value in opts:
            if option in ('-h', '--help'):
                raise _Usage(_helpMessage)
            elif option in ('-v', '--verbose'):
                global _verbose
                _verbose = True
            elif option in ('-t', '--team'):
                team = value
            elif option in ('-c', '--crawlerId'):
                crawlerId = value
            elif option in ('-d', '--dataDir'):
                dataDir = value
            elif option in ('-u', '--url'):
                url = value
            elif option in ('-i', '--index'):
                index = value
            elif option in ('-o', '--docType'):
                docType = value
            elif option in ('-p', '--path'):
                outPath = value
            elif option in ('-s', '--storeprefix'):
                storePrefix = value

        if team == None or crawlerId == None or dataDir == None or index == None or docType == None \
                or (outPath == None and url == None) or storePrefix == None:
            print("One or more arguments are missing or invalid")
            raise _Usage(_helpMessage)

        esIndex(dataDir, team, crawlerId, index, docType, url, outPath, storePrefix)

    except _Usage, err:
        print >>sys.stderr, sys.argv[0].split('/')[-1] + ': ' + str(err.msg)
        return 2

if __name__ == "__main__":
    sys.exit(main())
