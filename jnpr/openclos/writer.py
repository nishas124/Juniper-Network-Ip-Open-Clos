'''
Created on Aug 14, 2014

@author: preethi
'''
import pydot
import os
import logging
from jinja2 import Environment, PackageLoader
from model import InterfaceDefinition

cablingPlanTemplateLocation = os.path.join('conf', 'cablingPlanTemplates')

moduleName = 'writer'
logging.basicConfig()
logger = logging.getLogger(moduleName)
logger.setLevel(logging.DEBUG)

class WriterBase():
    def __init__(self, conf, pod, dao):
        if 'logLevel' in conf:
            logger.setLevel(logging.getLevelName(conf['logLevel'][moduleName]))        
        
        # use dao to generate various output
        self.dao = dao
        
        # this writer is specific for this pod
        self.pod = pod
        
        self.conf = conf
        
        # resolve output directory
        if 'outputDir' in conf:
            outputPath = conf['outputDir']
            self.outputDir = os.path.join(outputPath, pod.id+'-'+pod.name)
        else:
            self.outputDir = os.path.join('out', pod.id+'-'+pod.name)
        if not os.path.exists(self.outputDir):
            os.makedirs(self.outputDir)

class ConfigWriter(WriterBase):
    def __init__(self, conf, pod, dao):
        WriterBase.__init__(self, conf, pod, dao)
        
    def write(self, device, config):
        fileName = device.id + '-' + device.name
        logger.info('Writing config for device: %s' % (fileName))
        with open(os.path.join(self.outputDir, fileName + '.conf'), 'w') as f:
                f.write(config)

class DhcpConfWriter(WriterBase):
    def __init__(self, conf, pod, dao):
        WriterBase.__init__(self, conf, pod, dao)

    def write(self, dhcpConf):
        if dhcpConf is not None:
            logger.info('Writing dhcpd.conf for pod: %s' % (self.pod.name))
            with open(os.path.join(self.outputDir, 'dhcpd.conf'), 'w') as f:
                    f.write(dhcpConf)
        else:
            logger.error('No content, skipping writing dhcpd.conf for pod: %s' % (self.pod.name))

    def writeSingle(self, dhcpConf):
        if dhcpConf is not None:
            logger.info('Writing single dhcpd.conf for all pods')
            with open(os.path.join(self.outputDir, '..', 'dhcpd.conf'), 'w') as f:
                    f.write(dhcpConf)
        else:
            logger.error('No content, skipping writing single dhcpd.conf for all pods')

class CablingPlanWriter(WriterBase):
    def __init__(self, conf, pod, dao):
        WriterBase.__init__(self, conf, pod, dao)
        self.templateEnv = Environment(loader=PackageLoader('jnpr.openclos', cablingPlanTemplateLocation))
        #self.templateEnv.trim_blocks = True
        self.templateEnv.lstrip_blocks = True
        # load cabling plan template
        self.template = self.templateEnv.get_template(self.pod.topologyType + '.txt')
        # validity check
        if 'deviceFamily' not in self.conf:
            raise ValueError("No deviceFamily found in configuration file")

    def writeJSON(self):
        if self.pod.topologyType == 'threeStage':
            return self.writeJsonThreeStage()
        elif self.pod.topologyType == 'fiveStageRealEstate':
            return self.writeJSONFiveStageRealEstate()
        elif self.pod.topologyType == 'fiveStagePerformance':
            return self.writeJSONFiveStagePerformance()
            
    def writeJsonThreeStage(self):
        devices = []
        links = []
        for device in self.pod.devices:
            devices.append({'id': device.id, 'name': device.name, 'role': device.role})
            if device.role == 'leaf':
                leafPeerPorts = self.dao.Session().query(InterfaceDefinition).filter(InterfaceDefinition.device_id == device.id)\
                .filter(InterfaceDefinition.peer != None).order_by(InterfaceDefinition.name_order_num).all()
                for port in leafPeerPorts:
                    leafInterconnectIp = port.layerAboves[0].ipaddress #there is single IFL as layerAbove, so picking first one
                    spinePeerPort = port.peer
                    spineInterconnectIp = spinePeerPort.layerAboves[0].ipaddress #there is single IFL as layerAbove, so picking first one
                    links.append({'device1': device.name, 'port1': port.name, 'ip1': leafInterconnectIp, 
                                  'device2': spinePeerPort.device.name, 'port2': spinePeerPort.name, 'ip2': spineInterconnectIp})
        
        cablingPlanJSON = self.template.render(devices = devices, links = links)

        path = os.path.join(self.outputDir, 'cablingPlan.json')
        logger.info('Writing cabling plan: %s' % (path))
        with open(path, 'w') as f:
                f.write(cablingPlanJSON)

    def writeJSONFiveStageRealEstate(self):
        pass

    def writeJSONFiveStagePerformance(self):
        pass
        
    def writeDOT(self):
        if self.pod.topologyType == 'threeStage':
            return self.writeDOTThreeStage()
        elif self.pod.topologyType == 'fiveStageRealEstate':
            return self.writeDOTFiveStageRealEstate()
        elif self.pod.topologyType == 'fiveStagePerformance':
            return self.writeDOTFiveStagePerformance()
    
    def writeDOTThreeStage(self):
        '''
        creates DOT file for devices in topology which has peers
        '''
       
        topology = self.createLabelForDevices(self.pod.devices, self.conf['DOT'])
        colors = self.conf['DOT']['colors']
        i =0
        for device in self.pod.devices:
            linkLabel = self.createLabelForLinks(device)
            if(i == len(colors)): 
                i=0
                self.createLinksInGraph(linkLabel, topology, colors[i])
                i+=1
            else:
                self.createLinksInGraph(linkLabel, topology, colors[i])
                i+=1
            
        path = os.path.join(self.outputDir, 'cablingPlan.dot')
        logger.info('Writing cabling plan: %s' % (path))
        topology.write_raw(path)

    def createLabelForDevices(self, devices, conf):
        #create the graph 
        ranksep = conf['ranksep']
        topology = pydot.Dot(graph_type='graph', splines='polyline', ranksep=ranksep)
        for device in devices:
            label = self.createLabelForDevice(device)
            self.createDeviceInGraph(label, device, topology)
        return topology    
                
    def createLabelForDevice(self, device):
        label = '{'
      
        label = label + '{'
        for ifd in device.interfaces: 
            if type(ifd) is InterfaceDefinition: 
                if ifd.role == 'uplink':
                    if ifd.peer is not None:
                        label += '<'+ifd.id+'>'+ ifd.name+'|'
                    
        if label.endswith('|'):
            label = label[:-1]
            label += '}|{' + device.name + '}|{'
        else:
            label += device.name + '}|{'
            
        for ifd in device.interfaces:
            if type(ifd) is InterfaceDefinition:
                if ifd.role == 'downlink':
                    if ifd.peer is not None:
                        label += '<'+ifd.id+'>'+ ifd.name+'|'
                    
        if label.endswith('|'):
            label = label[:-1]
            label += '}}'
        else:
            label = label[:-2]
            label += '}'
            
        return label

    def createDeviceInGraph(self, labelStrs, device, testDeviceLabel):
        #create device in DOT graph
        testDeviceLabel.add_node(pydot.Node(device.id, shape='record', label= labelStrs))
            
    def createLabelForLinks(self, device):
        links = {}
                      
        for ifd in device.interfaces:
            if type(ifd) is InterfaceDefinition:
                if ifd.role == 'downlink':
                    if ifd.peer is not None: 
                        interface =  '"'+ device.id +'"'+ ':' +'"'+ ifd.id +'"'
                        peer = '"'+ifd.peer.device.id +'"' + ':' +'"'+ ifd.peer.id +'"'
                        links[interface] = peer
                       
        return links

    def createLinksInGraph(self, links, linksInTopology, color):
        #create peer links between the devices in DOT graph
        for interface, peer in links.iteritems():
            linksInTopology.add_edge(pydot.Edge(interface, peer,color=color))

    def writeDOTFiveStageRealEstate(self):
        pass
        
    def writeDOTFiveStagePerformance(self):
        pass
        
