import requests
import zipfile
import datetime
import xmltodict
import schedule
import os
import json
import time
import xml.etree.ElementTree as ET
from flask import Flask, jsonify
from multiprocessing import Process, Manager
from io import BytesIO

print('Starting puller for DfT BODS...')
app = Flask(__name__)

def fetchUpdate(operatorList=['GNEL']):
    print('Fetching update from DfT BODS...')

    try:
        r = requests.get('https://data.bus-data.dft.gov.uk/avl/download/bulk_archive')
    except:
        print('Unable to obtain updated bulk archive from DfT.')
        return

    zipdata = BytesIO()
    zipdata.write(r.content)

    print('Extracting ZIP data...')
    ziphandler = zipfile.ZipFile(zipdata)
    siri = ziphandler.open('siri.xml')

    print('Decoding ZIP file...')
    siriXml = siri.read().decode('utf-8')

    print('Parsing XML tree...')
    siriNode = ET.fromstring(siriXml)

    print('Processing XML data...')
    siriNs = 'http://www.siri.org.uk/siri'
    ns = {'siri': siriNs}

    activityLocal = []
    for op in operatorList:
        print('Finding vehicles for NOC code "%s"...' % op)
        operatorFilter = ".='%s'" % op
        xpathSelector = [
            'siri:ServiceDelivery',
            'siri:VehicleMonitoringDelivery',
            'siri:VehicleActivity',
            'siri:MonitoredVehicleJourney',
            'siri:OperatorRef[%s]' % operatorFilter,
            '..',
            '..'
        ]

        activityNodes = siriNode.findall('./%s' % '/'.join(xpathSelector), namespaces=ns)
        for activity in activityNodes:
            activityDict = xmltodict.parse(ET.tostring(activity, encoding='utf8', method='xml', default_namespace=siriNs))
            activityLocal.append(activityDict)

    print('Identified %u buses in the North East.' % len(activityLocal))

    return activityLocal
    #print(json.dumps(activityLocal, indent=2))

def update(operatorList, returns):
    activityLocal = fetchUpdate(operatorList=operatorList)
    returns['localBuses'] = activityLocal

def startUpdate(operatorList, returns):
    p = Process(target=update, args=(operatorList, returns,))
    p.start()


@app.route('/vm', methods=['GET'])
def serveBuses():
    global returns
    return jsonify(returns['localBuses'])

def scheduler(nocTable, returns):
    schedule.every(15).seconds.do(startUpdate, nocTable, returns)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    # List of operators to include, from the NOC tables
    nocTable = [
        # Go North East
        'GNEL',
        # Stagecoach North East
        'SCHA',
        'SCLV',
        'SCNE',
        'SCNS',
        'SCSS',
        'SCSU',
        'SCTE',
        # Arriva
        'ANEA',
        'ANUM',
        'ARDU'
    ]

    manager = Manager()
    returns = manager.dict()

    # Do an initial update
    startUpdate(operatorList=nocTable, returns=returns)

    # Start a separate process for handling future updates
    ps = Process(target=scheduler, args=(nocTable, returns, ))
    ps.start()

    # Start serving web requests
    from waitress import serve
    serve(app, host="0.0.0.0", port=5000)

