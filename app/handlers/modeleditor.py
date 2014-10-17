import logging
try:
  import json
except ImportError:
  from django.utils import simplejson as json
from google.appengine.ext import db
import pickle
import traceback
import re
import random
import time
from google.appengine.api import users

from stochssapp import BaseHandler
from stochss.model import *
from stochss.stochkit import *
from stochss.examplemodels import *
import stochss.converter

import webapp2
import exportimport

class ObjectProperty(db.Property):
    """  A db property to store objects. """

    def get_value_for_datastore(self, model_instance):
        result = super(ObjectProperty, self).get_value_for_datastore(model_instance)
        result = pickle.dumps(result)
        return db.Blob(result)

    def make_value_from_datastore(self, value):
        if value is None:
            return None
        return pickle.loads(value)

    def empty(self, value):
        return value is None


class StochKitModelWrapper(db.Model):
    """
    A wrapper for the StochKit Model object
    """
    user_id = db.StringProperty()
    name = db.StringProperty()
    species = ObjectProperty()
    reactions = ObjectProperty()
    isSpatial = db.BooleanProperty()
    units = db.StringProperty()
    spatial = ObjectProperty()
    zipFileName = db.StringProperty()
    is_public = db.BooleanProperty()

    def delete(self):
        if self.zipFileName:
            if os.path.exists(self.zipFileName):
                os.remove(self.zipFileName)

        super(StochKitModelWrapper, self).delete()

class ModelManager():
    @staticmethod
    def getModels(handler, modelAsString = True, noXML = False):
        models = db.GqlQuery("SELECT * FROM StochKitModelWrapper WHERE user_id = :1", handler.user.user_id()).run()

        output = []

        for modelDb in models:
            jsonModel = { "name" : modelDb.name,
                          "id" : modelDb.key().id(),
                          "units" : modelDb.units,
                          "species" : modelDb.species,
                          "reactions" : modelDb.reactions,
                          "isSpatial" : modelDb.isSpatial,
                          "spatial" : modelDb.spatial,
                          "is_public" : modelDb.is_public }

            output.append(jsonModel)

        return output

    @staticmethod
    def getModel(handler, model_id, modelAsString = True):
        modelDb = StochKitModelWrapper.get_by_id(int(model_id))

        if modelDb == None:
            return None

        jsonModel = { "name" : modelDb.name,
                      "id" : modelDb.key().id(),
                      "species" : modelDb.species,
                      "reactions" : modelDb.reactions,
                      "units" : modelDb.units,
                      "isSpatial" : modelDb.isSpatial,
                      "spatial" : modelDb.spatial,
                      "is_public" : modelDb.is_public }
                
        return jsonModel

    @staticmethod
    def getModelByName(handler, modelName, modelAsString = True, user_id = None):
        if not user_id:
            user_id = handler.user.user_id()

        model = db.GqlQuery("SELECT * FROM StochKitModelWrapper WHERE user_id = :1 AND name = :2", user_id, modelName).get()

        if model == None:
            return None

        jsonModel = { "name" : modelDb.name,
                      "id" : modelDb.key().id(),
                      "species" : modelDb.species,
                      "reactions" : modelDb.reactions,
                      "units" : modelDb.units,
                      "isSpatial" : modelDb.isSpatial,
                      "spatial" : modelDb.spatial,
                      "is_public" : modelDb.is_public }
                
        return jsonModel

    @staticmethod
    def createModel(handler, model, modelAsString = True, rename = None):
        userID = None

        # Set up defaults
        if 'isSpatial' not in model or 'spatial' not in model:
            model['isSpatial'] = False
            model['spatial'] = { 'subdomains' : [],
                                 'mesh_wrapper_id' : None,
                                 'species_diffusion_coefficients' : {} ,
                                 'species_subdomain_assignments' : {} ,
                                 'reactions_subdomain_assignments' : {},
                                 'initial_conditions' : {} }

        if 'is_public' not in model:
            model['is_public'] = False

        if 'user_id' in model:
            userID = model['user_id']
        else:
            userID = handler.user.user_id()

        # Make sure name isn't taken, or build one that isn't taken
        if "name" in model:
            tryName = model["name"]
            if tryName in [x.name for x in db.Query(StochKitModelWrapper).filter('user_id =', userID).run()]:
                if rename:
                    i = 1
                    tryName = '{0}_{1}'.format(model["name"], i)

                    while tryName in [x.name for x in db.Query(StochKitModelWrapper).filter('user_id =', userID).run()]:
                        i = i + 1
                        tryName = '{0}_{1}'.format(model["name"], i)
                else:
                    return None

        modelWrap = StochKitModelWrapper()

        if rename:
            model["name"] = tryName

        if "name" in model:
            name = model["name"]
        else:
            raise Exception("Why is this code here? modeleditor.py 185")
            #name = "tmpname"

        if 'isSpatial' in model:
            modelWrap.isSpatial = model['isSpatial']

        if 'spatial' in model:
            modelWrap.spatial = model['spatial']

        modelWrap.name = name

        modelWrap.species = model["species"]
        modelWrap.reactions = model["reactions"]
        modelWrap.spatial = model["spatial"]
        modelWrap.isSpatial = model["isSpatial"]
        modelWrap.is_public = model["is_public"]
        modelWrap.units = model["units"]
        modelWrap.user_id = userID

        return modelWrap.put().id()

    @staticmethod
    def deleteModel(handler, model_id):
        model = StochKitModelWrapper.get_by_id(model_id)
        model.delete()

    @staticmethod
    def updateModel(handler, jsonModel):
        modelWrap = StochKitModelWrapper.get_by_id(jsonModel["id"])

        if "name" not in jsonModel:
            raise Exception("Why is this code here?")

        modelWrap.user_id = handler.user.user_id()
        modelWrap.name = jsonModel["name"]
        modelWrap.species = jsonModel["species"]
        modelWrap.reactions = jsonModel["reactions"]
        modelWrap.spatial = jsonModel["spatial"]
        modelWrap.isSpatial = jsonModel["isSpatial"]
        modelWrap.is_public = jsonModel["is_public"]
        modelWrap.units = jsonModel["units"]

        return modelWrap.put().id()

class ModelBackboneInterface(BaseHandler):
    def get(self):
        req = self.request.path.split('/')[-1]
    
        self.response.content_type = 'application/json'
        
        if req == 'list':
            models = ModelManager.getModels(self, noXML = True)

            self.response.write(json.dumps(models))
        else:
            model = ModelManager.getModel(self, int(req))

            self.response.write(json.dumps(model))

    def post(self):
        jsonModel = json.loads(self.request.body)

        modelId = ModelManager.createModel(self, jsonModel, rename = True)

        self.response.content_type = "application/json"

        if modelId == None:
            self.response.set_status(500)
            self.response.write('')
        else:
            self.response.write(json.dumps(ModelManager.getModel(self, modelId)))

    def put(self):
        req = self.request.uri.split('/')[-1]

        modelId = int(req)
        jsonModel = json.loads(self.request.body)
        modelId = ModelManager.updateModel(self, jsonModel)

        self.response.content_type = "application/json"

        if modelId == None:
            self.response.write('Can\'t find model id ' + req)
            self.response.set_status(500)
        else:
            self.response.write(json.dumps(ModelManager.getModel(self, modelId)))

    def delete(self):
        model_id = self.request.uri.split('/')[-1]
      
        ModelManager.deleteModel(self, int(model_id))
      
        self.response.content_type = "application/json"
        self.response.write(json.dumps([]))

class ModelConvertPage(BaseHandler):
    def authentication_required(self):
        return True
    
    def get(self):
        self.render_response('convert.html')

class ModelEditorPage(BaseHandler):
    """
        
    """        
    def authentication_required(self):
        return True
    
    def get(self):
        self.render_response('modeleditor.html')
