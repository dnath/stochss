try:
  import json
except ImportError:
  from django.utils import simplejson as json

import traceback
import re
from collections import OrderedDict
import fileserver
import shlex
import sys
import pyurdme
import tempfile
import shutil

from stochssapp import *
from stochss.model import *

#import modeleditor.ObjectProperty

#right here

class MeshWrapper(db.Model):
    userId = db.StringProperty()
    name = db.StringProperty()
    description = db.TextProperty()
    meshFileId = db.IntegerProperty()
    subdomainsFileId = db.IntegerProperty()
    ghost = db.BooleanProperty()
    undeletable = db.BooleanProperty()

    def toJSON(self):
        return { "userId" : self.userId,
                 "name" : self.name,
                 "description" : self.description,
                 "meshFileId" : self.meshFileId,
                 "subdomainsFileId" : self.subdomainsFileId,
                 "ghost" : self.ghost,
                 "undeletable" : self.undeletable,
                 "id" : self.key().id() }

    def delete(self):
        try:
            fileserver.FileManager.deleteFile(self, self.meshFileId)
        except IOError as error:
            sys.stderr.write('Failed to delete meshFile {0} in meshwrapper destructor\n'.format(self.meshFileId))

        try:
            fileserver.FileManager.deleteFile(self, self.subdomainsFileId)
        except IOError as error:
            sys.stderr.write('Failed to delete subdomainsFile {0} in meshwrapper destructor\n'.format(self.subdomainsFileId))

        super(MeshWrapper, self).delete()
    
def int_or_float(s):
    try:
        return int(s)
    except ValueError:
        return float(s)

class MeshEditorPage(BaseHandler):

    def authentication_required(self):
        return True
    
    def get(self):
        try:
            if True == True:
                base = os.path.dirname(os.path.realpath(__file__)) + '/../static/spatial/'
                files = [ 'coli_with_membrane_mesh.xml',
                          'cylinder_mesh.xml',
                          'unit_cube_with_membrane_mesh.xml',
                          'unit_sphere_with_membrane_mesh.xml' ]
                
                descriptions = { 'coli_with_membrane_mesh.xml' : 'Mesh for simulation of the E. coli or similar rod-shaped bacteria.',
                                 'cylinder_mesh.xml' : 'Mesh for simulations in a cylindrical domain.',
                                 'unit_cube_with_membrane_mesh.xml' : 'Simulations on a unit cube domain.',
                                 'unit_sphere_with_membrane_mesh.xml' : 'Simulations on a unit sphere domain.' }
                
                namesToFilenames = { 'E-coli with membrane' : 'coli_with_membrane_mesh.xml',
                                     'Cylinder' : 'cylinder_mesh.xml',
                                     'Unit cube' : 'unit_cube_with_membrane_mesh.xml',
                                     'Unit sphere' : 'unit_sphere_with_membrane_mesh.xml' }
            
                converted = set()
                for wrapper in db.GqlQuery("SELECT * FROM MeshWrapper WHERE userId = :1", self.user.user_id()).run():
                    converted.add(wrapper.name)

                for name in set(namesToFilenames.keys()) - converted:
                    fileName = namesToFilenames[name]

                    meshDb = MeshWrapper()
                
                    # To get the subdomains, there is a .txt file stored along with every .xml
                    baseName, ext = os.path.splitext(fileName)
                    subdomainsFile = open(os.path.join(base, baseName + '.txt'), 'r')
                    subdomainsFileId = fileserver.FileManager.createFile(self, "subdomainsFiles", baseName + '.txt', subdomainsFile.read(), 777)
                    subdomainsFile.close()
                    
                    meshFile = open(os.path.join(base, fileName), 'r')
                    meshFileId = fileserver.FileManager.createFile(self, "meshFiles", fileName, meshFile.read(), 777)
                    meshFile.close()

                    meshDb.userId = self.user.user_id()
                    meshDb.name = name
                    meshDb.description = descriptions[fileName]
                    meshDb.meshFileId = int(meshFileId)
                    meshDb.subdomainsFileId = int(subdomainsFileId)
                    meshDb.undeletable = True
        
                    meshDb.put()
            
                #return

            reqType = self.request.get('reqType')
            if reqType == "getMeshInfo":
                self.response.content_type = 'application/json'
                model_edited = self.get_session_property('model_edited')

                if model_edited == None:
                    self.render_response('modeleditor/mesheditor.html')
                    return

                row = db.GqlQuery("SELECT * FROM StochKitModelWrapper WHERE user_id = :1 AND model_name = :2", self.user.user_id(), model_edited.name).get()

                if row is None:
                    self.render_response('modeleditor/mesheditor.html')
                    return

                meshWrappers = []
                for wrapperRow in db.GqlQuery("SELECT * FROM MeshWrapper").run():
                    meshWrappers.append( wrapperRow.toJSON() )

                # Try to get selected mesh
                try:
                    selectedMesh = MeshWrapper.get_by_id(row.spatial['mesh_wrapper_id'])
                    selectedMeshJSON = selectedMesh.toJSON()
                # If anything goes wrong (mesh deleted, no mesh on model), return None
                except:
                    selectedMeshJSON = None

                data = { 'meshes' : meshWrappers,
                         'meshWrapperId' : row.spatial['mesh_wrapper_id'],
                         'selectedMesh' : selectedMeshJSON,
                         'subdomains' : row.spatial['subdomains'],
                         'initialConditions' : row.spatial['initial_conditions'],
                         'reactionsSubdomainAssignments' : row.spatial['reactions_subdomain_assignments'],
                         'speciesSubdomainAssignments' : row.spatial['species_subdomain_assignments'] }
                
                self.response.write( json.dumps( data ) )
                return
            else:
                model_edited = self.get_session_property('model_edited')

                if model_edited == None:
                    self.render_response('modeleditor/mesheditor.html')
                    return

                row = db.GqlQuery("SELECT * FROM StochKitModelWrapper WHERE user_id = :1 AND model_name = :2", self.user.user_id(), model_edited.name).get()

                if row is None:
                    self.render_response('modeleditor/mesheditor.html')
                    return

                all_species = row.model.getAllSpecies()
            
                data = { "name" : row.model.name, "units" : row.model.units, "isSpatial" : row.isSpatial, "spatial" : row.spatial }
            
                if all_species is not None:
                    self.render_response('modeleditor/mesheditor.html', **data)
                else:
                    self.render_response('modeleditor/mesheditor.html')
        except Exception, error:
            traceback.print_exc()
            result = { "status" : False,
                       "msg" : 'Internal StochSS error: {0}'.format(error) }
            self.error(500)
            self.response.headers['Content-Type'] = 'application/json'
            self.response.write(json.dumps(result))

    def post(self):
        try:
            # First, check to see if it's an update request and then route it to the appropriate function.
            reqType = self.request.get('reqType')
            self.response.content_type = 'application/json'

        
            model_edited = self.get_session_property('model_edited')
            if model_edited == None:
                self.render_response('modeleditor/specieseditor.html')
                return

            row = db.GqlQuery("SELECT * FROM StochKitModelWrapper WHERE user_id = :1 AND model_name = :2", self.user.user_id(), model_edited.name).get()

            if row is None:
                self.render_response('modeleditor/specieseditor.html')
                return

            if self.request.get('reqType') == 'setMesh':
                # Looks like a speciesSubdomainAssignments request
                self.response.content_type = 'application/json'

                #print 'QWTASDFFASDFASDFSDAJKL;FSADFDSAJKL;FASD'
            
                data = json.loads( self.request.get('data') );

                meshWrapperId = data['meshWrapperId']

                # Acquire updated subdomains (if there are any)
                meshDb = MeshWrapper.get_by_id(meshWrapperId)

                meshFile = fileserver.FileManager.getFile(self, meshDb.meshFileId)
                
                row.spatial['subdomains'] = []
                if meshDb.subdomainsFileId:
                    sdFile = fileserver.FileManager.getFile(self, meshDb.subdomainsFileId)
                    newSubdomains = set()

                    sdHandle = open(sdFile['storePath'], 'r')
                    for line in sdHandle:
                        v, l = line.strip().split(',')
                
                        l = int(float(l))
                
                        newSubdomains.add(l)

                    sdHandle.close()

                    row.spatial['subdomains'] = list(newSubdomains)

                    row.spatial['species_subdomain_assignments'] = {}
                    row.spatial['reactions_subdomain_assignments'] = {}

                    for speciesId in row.model.listOfSpecies.keys():
                        row.spatial['species_subdomain_assignments'][speciesId] = list(newSubdomains)

                    for reactionId in row.model.listOfReactions.keys():
                        row.spatial['reactions_subdomain_assignments'][reactionId] = list(newSubdomains)
                else:
                    row.spatial['subdomains'] = [1]

                    for speciesId in row.spatial['species_subdomain_assignments']:
                        row.spatial['species_subdomain_assignments'][speciesId] = [1]

                    for reactionId in row.spatial['reactions_subdomain_assignments']:
                        row.spatial['reactions_subdomain_assignments'][reactionId] = [1]

                    row.spatial['initial_conditions'] = {}

                row.spatial['mesh_wrapper_id'] = meshWrapperId

                row.put()
            
                meshWrappers = []
                for wrapperRow in db.GqlQuery("SELECT * FROM MeshWrapper").run():
                    meshWrappers.append( wrapperRow.toJSON() )

                data = { 'meshes' : meshWrappers,
                         'meshWrapperId' : row.spatial['mesh_wrapper_id'],
                         'selectedMesh' : meshDb.toJSON(),
                         'subdomains' : row.spatial['subdomains'],
                         'initialConditions' : row.spatial['initial_conditions'],
                         'reactionsSubdomainAssignments' : row.spatial['reactions_subdomain_assignments'],
                         'speciesSubdomainAssignments' : row.spatial['species_subdomain_assignments'] }

                self.response.write(json.dumps( data ))
                return
            if self.request.get('reqType') == 'setName':
                # Looks like a speciesSubdomainAssignments request
                self.response.content_type = 'application/json'

                data = json.loads( self.request.get('data') );

                meshWrapperId = data['id']

                meshDb = MeshWrapper.get_by_id(meshWrapperId)

                meshDb.name = data['newName']
                
                meshDb.put()
            
                self.response.write(json.dumps( { "statu" : True,
                                                  "msg" : 'Name updated' } ))
                return
            elif self.request.get('reqType') == 'getMesh':
                data = json.loads( self.request.get('data') );

                meshWrapperDb = MeshWrapper.get_by_id(data['id'])
                meshFileObj = fileserver.FileManager.getFile(self, meshWrapperDb.meshFileId)
                meshFileName = meshFileObj["storePath"]

                colors = None
                if meshWrapperDb.subdomainsFileId != None:
                    subdomainFileObj = fileserver.FileManager.getFile(self, meshWrapperDb.subdomainsFileId)
                    meshSubdomainFileName = subdomainFileObj["storePath"]

                    subdomains = []
                    fhandle = open(meshSubdomainFileName, 'r')
                    for line in fhandle.read().split():
                        v, s = line.strip().split(',')

                        v = int(v)
                        s = int(float(s))

                        subdomains.append((v, s))
                    fhandle.close()

                    subdomains = [y for x, y in sorted(subdomains, key = lambda x : x[0])]

                    colors = []
                    print data['selectedSubdomains']
                    for subdomain in subdomains:
                        if subdomain in data['selectedSubdomains']:
                            colors.append('red')
                        else:
                            colors.append('black')

                if colors:
                    threejs = pyurdme.URDMEMesh.read_dolfin_mesh(str(meshFileName)).export_to_three_js(colors = colors)
                else:
                    threejs = pyurdme.URDMEMesh.read_dolfin_mesh(str(meshFileName)).export_to_three_js()

                self.response.write( threejs )
                return
            elif self.request.get('reqType') == 'deleteMesh':
                data = json.loads( self.request.get('data') );
                meshWrapperDb = MeshWrapper.get_by_id(data['id'])

                meshWrapperDb.delete()

                self.response.write( { "status" : False, "msg" : "Mesh deleted" })
                return
            elif self.request.get('reqType') == 'setInitialConditions':
                data = json.loads( self.request.get('data') );

                row.spatial['initial_conditions'] = data['initialConditions']

                #print data['initialConditions']
                #print row.spatial['initial_conditions']

                row.put()

                self.response.write( json.dumps( { "status" : True, "msg" : "Initial conditions updated" } ) )
                return
            elif reqType == 'addMeshWrapper':
                meshDb = MeshWrapper()
                data = json.loads(self.request.get('data'))

                meshFile = fileserver.FileManager.getFile(self, data['meshFileId'])
                basename, ext = os.path.splitext(meshFile['path'])

                meshDb.userId = self.user.user_id()
                meshDb.name = data['name']
                meshDb.description = data['description']
                meshDb.meshFileId = data['meshFileId']
                meshDb.subdomainsFileId = data['subdomainsFileId'] if 'subdomainsFileId' in data else None
                meshDb.ghost = False
                meshDb.undeletable = False
                
                meshDb.put()
                
                self.response.write( json.dumps( meshDb.toJSON() ) )
                return
        except Exception, error:
            traceback.print_exc()
            result = { "status" : False,
                       "msg" : 'Internal StochSS error: {0}'.format(error) }
            self.error(500)
            self.response.headers['Content-Type'] = 'application/json'
            self.response.write(json.dumps(result))
