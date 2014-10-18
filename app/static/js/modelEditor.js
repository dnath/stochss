var ModelEditor = ModelEditor || {}

var modelData = {
    species : { species0 : { name : "s1", initialCondition : 1000 }, species1 : { name : "s2", initialCondition : 51202 } },
    reactions : { "reaction0" :
                  { name : "reaction0",
                    reactants : { s1 : { name : "species1", stoichiometry : 2 } },
                    rate : 0,
                    products : {},
                    type : 'massaction'},
                  "reaction1" :
                  { name : "reaction1",
                    type : 'massaction',
                    rate : 1,
                    reactants : {},
                    products : { s1 : { name : "species1", stoichiometry : 2 } } }
                },

    units : "population",
    name : "dimer_decay",
    isSpatial : false
};

var getNewMemberName = function(dict, baseName)
{
    var i = 0;

    var tmpName = baseName + i.toString();

    while(_.has(dict, tmpName))
    {
        i += 1;
        tmpName = baseName + i.toString();
    }

    return tmpName;
};

var ModelType = Backbone.Model.extend(
    {}
);

var ModelCollection = Backbone.Collection.extend( {
    url: "/newModels/list",
    model: ModelType
});

//var models = [model]

ModelEditor.Selector = Backbone.View.extend(
    {
        events: {
            "click #addModelButton"  : "addModel"
        },

        initialize : function(attributes)
        {
            // Set up room for the model select stuff
            // Pull in all the models from the internets
            // Build the simulationConf page (don't need external info to make that happen)
            this.attributes = attributes;

            this.controller = this.attributes.controller;

            this.$el = $("#modelEditor");

            // Go off and fetch those models and queue up a render on completion
            this.models = new stochkit.ModelCollection();

            $( '.controller' ).hide();

            this.selectTemplate = _.template('<tr> \
  <td> \
    <input type="radio" name="model" /> \
  </td> \
  <td> \
    <%= name %> \
  </td> \
  <td> \
    <%= units %> \
  </td> \
  <td> \
    <% if(isSpatial) { %> \
      True \
    <% } else { %> \
      False \
    <% } %> \
  </td> \
  <td> \
    <button type=\"button\" class=\"btn btn-default delete\"> \
      <i class=\"icon-remove\"></i></span> \
    </button> \
  </td> \
</tr>');

            // When finished, queue up a render so folks have something to see
            this.models.fetch({ success : _.bind(this.render, this),
                                error : _.bind(this.modelsDownloadError, this) } );
        },

        addModel : function()
        {
            // Make sure model name unique
            var checkUnique = _.bind(function(name)
            { 
                var unique = true;

                for(var i = 0; i < this.models.length; i++)
                {
                    if(this.models.at(i).attributes.name == name)
                    {
                        unique = false;
                        break;
                    }
                }

                return unique;
            }, this);

            var i = 0
            var tmpName = modelData['name'];
            while(!checkUnique(tmpName))
            {
                tmpName = modelData['name'] + i;
                i++;
            }

            newData = _.clone(modelData);

            newData['name'] = tmpName;

            //Add the model and save to server
            this.models.add([newData]);
            var added = this.models.at(this.models.length - 1);

            //Create GUI elements
            var row = $( this.selectTemplate(added.attributes) ).appendTo($( '.selectorTableBody' ));

            var radioButton = row.find('input');
            var button = row.find('button');

            added.save({ success : _.bind(_.partial(this.modelAdded, button), this) ,
                         error : _.bind(_.partial(this.modelNotAdded, button), this) });

            button.click(_.bind(_.partial(this.destroyModel, added, row), this));
            radioButton.click(_.bind(_.partial(this.setModel, added), this));
        },

        destroyModel : function(model, row)
        {
            model.destroy();
            row.remove();
        },

        modelsDownloadError : function(model, response, options)
        {
            // Do something
            console.log('Failed to download models list');
        },

        setModel : function(model)
        {
            this.controller.setModel(model);
            $( '.controller' ).show();
        },

        render : function()
        {
            console.log('time to render');

            for(var i = 0; i < this.models.length; i++)
            {
                var row = $( this.selectTemplate(this.models.at(i).attributes) ).appendTo($( '.selectorTableBody' ));

                var button = row.find('button');
                var radioButton = row.find('input');

                radioButton.click(_.bind(_.partial(this.setModel, this.models.at(i)), this));
                button.click(_.bind(_.partial(this.destroyModel, this.models.at(i), row), this));
            }
        }
    }
);

ModelEditor.Controller = Backbone.View.extend(
    {
        events: {
            "click #addSpeciesButton"  : "addSpecies",
            "click #addReactionButton" : "addReaction",
            "click #addMichaelisMentonReactionButton" : "addMichaelisMentonReaction"
        },

        initialize : function(attributes)
        {
            // Set up room for the model select stuff
            // Pull in all the models from the internets
            // Build the simulationConf page (don't need external info to make that happen)
            this.attributes = attributes;

            this.$el = $("#modelEditor");

            //this.on('select', _.bind(this.select, this) );
            this.currentReaction = null;

            $( '.initialData' ).hide();
            $( '.trajectories' ).hide();
        },

        saveModel : _.throttle(function() {
            this.model.save();
        }, 500),

        setModel : function(model)
        {
            // When finished, execute a render so folks have something to see
            this.model = model;

            this.render();
        },

        modelDownloadError : function(model, response, options)
        {
            // Make a valid error here
        },

        addSpeciesDom : function(specieHandle, model)
        {
            var model = this.model.attributes;

            var specieTableTemplate =
"<tr> \
  <td> \
    <button type=\"button\" class=\"btn btn-default delete\"> \
      <i class=\"icon-remove\"></i> \
    </button> \
  </td> \
  <td> \
    <input class=\"name\" /> \
  </td> \
  <td> \
    <input class=\"value\" /> \
  </td> \
</tr>";

            //var specie = model.species[specieHandle];

            var template = _.template(specieTableTemplate);

            var newOption = $( template() ).appendTo( this.$el.find( "#speciesTableBody" ) );

            var deleteButton = newOption.find( '.delete' );
            var nameBox = newOption.find( '.name' );
            var valueBox = newOption.find( '.value' );

            nameBox.val(model.species[specieHandle].name);
            valueBox.val(model.species[specieHandle].initialCondition);

            // When clicked, this button removes the element
            deleteButton.on('click', _.bind(_.partial(function(specieHandle, model, doms, event) {
                //Make sure that the species is not in use
                var inuse = false;
                var usingReaction = null;
                for(var reactionKey in model.reactions)
                {
                    var reaction = model.reactions[reactionKey];

                    if(reaction.type == 'massaction')
                    {
                        for(var reactantKey in reaction.reactants)
                        {
                            if(reaction.reactants[reactantKey].name == specieHandle)
                            {
                                inuse = true;
                                usingReaction = reaction.name;
                                break;
                            }
                        }

                        for(var productKey in reaction.products)
                        {
                            if(reaction.products[productKey].name == specieHandle)
                            {
                                inuse = true;
                                usingReaction = reaction.name;
                                break;
                            }
                        }
                    }
                    else if(reaction.type == 'michaelismenton')
                    {
                        if(reaction.reactant == specieHandle)
                        {
                            inuse = true;
                            usingReaction = reaction.name;
                            break;
                        }

                        if(reaction.product == specieHandle)
                        {
                            inuse = true;
                            usingReaction = reaction.name;
                            break;
                        }

                        for(var extra in reaction.extras)
                        {
                            if(reaction.extras[extra].name == specieHandle)
                            {
                                inuse = true;
                                usingReaction = reaction.name;
                                break;
                            }
                        }
                    }

                    if(inuse)
                        break;
                }

                // Redraw the reaction editor
                if(inuse)
                {
                    this.speciesMsg( false, "Species cannot be deleted because it is in use by reaction \'" + usingReaction + "\'");
                }
                else
                {
                    delete model.species[specieHandle];
                    
                    for(var i in doms)
                    {
                        doms[i].remove();
                    }

                    this.addReactionEditorDom(this.currentReaction, this.model.attributes);
                    this.speciesMsg( true, "Species deleted");
                }
            }, specieHandle, model, [deleteButton, nameBox, valueBox, newOption]), this));

            // This function will handle values in the name box changing
            nameBox.on('change', _.bind(_.partial(this.handleSpeciesNameChange, specieHandle, model), this));
            
            // This function will handle values in the value box changing
            valueBox.on('change', _.bind(_.partial(this.handleSpeciesValueChange, specieHandle, model), this));
        },

        handleSpeciesNameChange : function(specieHandle, model, event) {
            var name = $( event.target ).val().trim();

            // Check if name is already in use
            var inuse = false;
            var names = [];
            for(var specie in model.species)
            {
                if(name == model.species[specie].name)
                {
                    inuse = true;
                    break;
                }
            }

            // Validate name
            if(!/^[a-zA-Z_][a-zA-Z0-9_]+$/.test(name))
            {
                this.speciesMsg(false, "Species name must be letters (a-z and A-Z), underscores, and numbers only and start with a letter or an underscore");
            }
            // Make sure it's not in use
            else if(inuse)
            {
                this.speciesMsg(false, "Species name must be unique");
            }
            // Change the name!
            else
            {
                model.species[specieHandle].name = name;

                this.addReactionEditorDom(this.currentReaction, this.model.attributes);
                
                this.speciesMsg(true, "Species name set");

                this.saveModel();
            }
        },

        handleSpeciesValueChange : function(specieHandle, model, event) {
            var val = $( event.target ).val().trim();
            
            // Validate input
            if(isNaN(val))
            {
                this.speciesMsg(false, "Input value for species " + specieHandle + " not understood");
            }
            // Make sure it's not in use
            else if(model.type == 'population' && !/^[0-9]+$/.test(val))
            {
                this.speciesMsg(false, "Input value for species " + specieHandle + " must be an integer");
            }
            // Change the value!
            else
            {
                model.species[specieHandle].initialCondition = parseFloat(val);
                
                this.speciesMsg(true, "Species " + specieHandle + " value set to " + parseFloat(val).toString());

                this.saveModel();
            }
        },

        speciesMsg : function( status, msg )
        {
            var msgBox = this.$el.find( "#speciesStatusDiv" );

            msgBox.text(msg);
            if(status)
                msgBox.prop('class', 'alert alert-success');
            else
                msgBox.prop('class', 'alert alert-danger');

            msgBox.show();
        },
        
        // This event gets fired when the user selects a csv data file
        initialDataSelectPreview : function(data)
        {
        },
        
        // This event gets fired when the user selects a csv data file
        trajectoriesSelectPreview : function(rawText)
        {
        },

        addSpecies : function()
        {
            var newHandle = getNewMemberName(this.model.attributes.species, 'specie');
                
            this.model.attributes.species[newHandle] = { name : newHandle,
                                                     initialCondition : 0 };

            this.addSpeciesDom(newHandle, this.model.attributes);

            this.addReactionEditorDom(this.currentReaction, this.model.attributes);

            this.saveModel();
        },

        // The following code handles the addition/subtraction of Reactions from the reactions
        //   table.
        addReactionsDom : function(reactionHandle, model)
        {
            var model = this.model.attributes;

            var reactionsTableTemplate =
"<tr> \
  <td> \
    <button type=\"button\" class=\"btn btn-default delete\"> \
      <i class=\"icon-remove\"></i> \
    </button> \
  </td> \
  <td> \
    <input class=\"name\" /> \
  </td> \
  <td> \
    <span class=\"type\"></span> \
  </td> \
  <td> \
    <button type=\"button\" class=\"btn btn-default edit\"> \
      <i class=\"icon-remove\"></i> \
    </button> \
  </td> \
</tr>";

            var reaction = model.reactions[reactionHandle];

            var template = _.template(reactionsTableTemplate);

            var newOption = $( template() ).appendTo( this.$el.find( "#reactionsTableBody" ) );

            var deleteButton = newOption.find( '.delete' );
            var nameBox = newOption.find( '.name' );
            var typeTextBox = newOption.find( '.type' );
            var editButton = newOption.find( '.edit' );

            nameBox.val(model.reactions[reactionHandle].name);

            var type = ""

            if(model.reactions[reactionHandle].type == 'massaction')
            {
                type = "Mass action";
            }
            else if(model.reactions[reactionHandle].type == 'custom')
            {
                type = "Custom propensity";
            }
            else if(model.reactions[reactionHandle].type == 'michaelismenton')
            {
                type = "Michaelis Menton";
            }

            typeTextBox.html(type);

            // When clicked, this event handler is responsible for removing all the dom elements
            //   added above as well as the reaction from the model
            deleteButton.on('click', _.partial(function(reactionHandle, model, doms, event) {
                delete model.reactions[reactionHandle];

                for(var i in doms)
                {
                    doms[i].remove();
                } 
            }, reactionHandle, model, [deleteButton, nameBox, typeTextBox, editButton, newOption]));

            // This function will handle values in the name box changing
            nameBox.on('change', _.bind(_.partial(this.handleReactionsNameChange, reactionHandle, model), this));

            // When clicked, the edit button needs to create the reaction editor box
            editButton.on('click', _.bind(_.partial(function(reactionHandle, model, event) {
                this.addReactionEditorDom(reactionHandle, model);
            }, reactionHandle, model), this));
        },

        handleReactionsNameChange : function(reactionHandle, model, event) {
            var name = $( event.target ).val().trim();

            // Check if name is already in use
            var inuse = false;
            var names = [];
            for(var reaction in model.reactions)
            {
                if(name == model.reactions[reaction].name)
                {
                    inuse = true;
                    break;
                }
            }

            // Validate name
            if(!/^[a-zA-Z_][a-zA-Z0-9_]+$/.test(name))
            {
                this.reactionsMsg(false, "Reaction me must be letters (a-z and A-Z), underscores, and numbers only and start with a letter or an underscore");
            }
            // Make sure it's not in use
            else if(inuse)
            {
                this.reactionsMsg(false, "Species name must be unique");
            }
            // Change the name!
            else
            {
                model.reactions[reactionHandle].name = name;
                
                this.reactionsMsg(true, "Species name set");

                this.saveModel();
            }
        },

        reactionsMsg : function( status, msg )
        {
            var msgBox = this.$el.find( "#reactionStatusDiv" );

            msgBox.text(msg);
            if(status)
                msgBox.prop('class', 'alert alert-success');
            else
                msgBox.prop('class', 'alert alert-danger');

            msgBox.show();
        },

        addReaction : function()
        {
            var newHandle = getNewMemberName(this.model.attributes.reactions, 'reaction');
                
            this.model.attributes.reactions[newHandle] = { name : newHandle,
                                                       reactants : {},
                                                       products : {},
                                                       type : 'massaction' };

            this.addReactionsDom(newHandle, this.model.attributes);

            this.saveModel();
        },

        addMichaelisMentonReaction : function()
        {
            var newHandle = getNewMemberName(this.model.attributes.reactions, 'reaction');

            var reactant = null, product = null;

            for(var species in this.model.attributes.species)
            {
                if(reactant == null)
                {
                    reactant = species;
                }
                else
                {
                    product = species;
                    break;
                }
            }

            this.model.attributes.reactions[newHandle] = { name : newHandle,
                                                       reactant : reactant,
                                                       product : product,
                                                       extras : {},
                                                       vRate : 0,
                                                       KmRate : 0,
                                                       type : 'michaelismenton' };

            this.addReactionsDom(newHandle, this.model.attributes);

            this.saveModel();
        },

        // The following code handles the drawing/removal of the mass-action editor
        //   This means adding the code for the reactants editor, the products editor, and
        //   The propensity stufffff
        addReactionEditorDom : function(reactionHandle, model)
        {
            this.currentReaction = reactionHandle;

            // If null is passed in, don't render anything
            if(this.currentReaction == null)
            {
                return;
            }

            var model = this.model.attributes;
            var reaction = model.reactions[reactionHandle];

            if(reaction.type == 'massaction')
            {
                // Acquire the mass action template
                //    Need to fill in 3 things:
                //    Reactant selector
                //    Product selector
                //    Rate box
                var template = _.template($( "#massActionTemplate" ).html());

                this.$el.find( "#reactionEditorDiv" ).empty();

                var reactionEditor = $( '<div>' ).appendTo( this.$el.find( "#reactionEditorDiv" ) ).html( template() );
                var reactantAndProductSelectDiv = reactionEditor.find( '.reactantAndProductSelectDiv' );

                var reactantSelector = $( '<div>' ).appendTo( reactantAndProductSelectDiv ).html( $( "#reactantsTemplate" ).html() );
                var productSelector = $( '<div>' ).appendTo( reactantAndProductSelectDiv ).html( $( "#productsTemplate" ).html() );


                var reactantAddButton = reactantSelector.find( '.add' );
                var productAddButton = productSelector.find( '.add' );
                var rateBox = reactionEditor.find( '.rate' );

                rateBox.val(model.reactions[reactionHandle].rate);

                // This function will handle values in the name box changing
                rateBox.on('change', _.bind(_.partial(this.handleReactionRateChange, reactionHandle, model), this));

                reactantAddButton.on('click', _.bind(_.partial(this.handleReactantAddButton, reactionHandle, model), this));
                productAddButton.on('click', _.bind(_.partial(this.handleProductAddButton, reactionHandle, model), this));

                // To build the reactant selector
                //    addReactant button

                for(var reactant in model.reactions[reactionHandle].reactants)
                {
                    this.addReactantDom(reactant, reactionHandle, model);
                }

                for(var product in model.reactions[reactionHandle].products)
                {
                    this.addProductDom(product, reactionHandle, model);
                }
            }
            else
            {
                // Acquire the template
                //    Need to fill in 3 things:
                //    Reactant selector
                //    Product selector
                //    Extra Interactions table
                //  For events need reactant/product change events and add button
                var template = _.template($( "#michaelisMentonTemplate" ).html());

                this.$el.find( "#reactionEditorDiv" ).empty();

                var reactionEditor = $( '<div>' ).appendTo( this.$el.find( "#reactionEditorDiv" ) ).html( template() );

                var reactantSelector = reactionEditor.find( ".reactantSelect" );
                var productSelector = reactionEditor.find( ".productSelect" );

                var extraTable = reactionEditor.find( '.extraTable' );
                var vBox = reactionEditor.find( '.v' );
                var KmBox = reactionEditor.find( '.Km' );

                var addExtraButton = reactionEditor.find( '.add' );

                vBox.val(model.reactions[reactionHandle].vRate);
                KmBox.val(model.reactions[reactionHandle].KmRate);
                
                // This function will handle values in the name box changing
                vBox.on('change', _.bind(_.partial(this.handleVRateChange, reactionHandle, model), this));
                KmBox.on('change', _.bind(_.partial(this.handleKmRateChange, reactionHandle, model), this));
                
                addExtraButton.on('click', _.bind(_.partial(this.handleExtraAddButton, reactionHandle, model), this));

                var reac = $( "<option value=\"\">null</option>").appendTo( reactantSelector );

                var prod = $( "<option value=\"\">null</option>").appendTo( productSelector );

                if(model.reactions[reactionHandle].reactant == '')
                {
                    reac.prop('selected', true);
                }
                
                if(model.reactions[reactionHandle].product == '')
                {
                    prod.prop('selected', true);
                }
                
                //    reactantSelector, productSelector
                for(specie in model.species) {
                    var reac = $( "<option value=\"" + specie + "\">" + model.species[specie].name + " </option>").appendTo( reactantSelector );

                    var prod = $( "<option value=\"" + specie + "\">" + model.species[specie].name + " </option>").appendTo( productSelector );
                    
                    if(model.reactions[reactionHandle].reactant == specie)
                    {
                        reac.prop('selected', true);
                    }
                    
                    if(model.reactions[reactionHandle].product == specie)
                    {
                        prod.prop('selected', true);
                    }
                }

                // Add on select change DOM calling handleReactantSelectChange
                reactantSelector.on('change', _.bind(_.partial(this.handleMichaelisMentonReactantSelectChange, reactionHandle, model), this));

                // Add on select change DOM calling handleReactantSelectChange
                productSelector.on('change', _.bind(_.partial(this.handleMichaelisMentonProductSelectChange, reactionHandle, model), this));

                for(var extra in model.reactions[reactionHandle].extras)
                {
                    this.addExtraDom(extra, reactionHandle, model);
                }

                this.updateMichaelisMentonPreview(reactionHandle, model);
            }
        },

        handleReactantAddButton : function(reactionHandle, model, event) {
            var reactantHandle = getNewMemberName(model.reactions[reactionHandle].reactants, 'r');   

            // If the next 6 lines seem weird, it's cause they are
            //    extract any valid species name
            var reactantName;

            for(var specie in model.species)
            {
                reactantName = model.species[specie].name;
                break;
            }
            
            model.reactions[reactionHandle].reactants[reactantHandle] = { name : reactantName, stoichiometry : 2 };
           
            this.addReactantDom(reactantHandle, reactionHandle, model);

            this.saveModel();
        },

        handleProductAddButton : function(reactionHandle, model, event) {
            var productHandle = getNewMemberName(model.reactions[reactionHandle].products, 'p');   

            // If the next 6 lines seem weird, it's cause they are
            //    extract any valid species name
            var productName;
            
            for(var specie in model.species)
            {
                productName = model.species[specie].name;
                break;
            }
            
            model.reactions[reactionHandle].products[productHandle] = { name : productName, stoichiometry : 2 };
           
            this.addProductDom(productHandle, reactionHandle, model);

            this.saveModel();
        },

        addReactantDom : function(reactantHandle, reactionHandle, model)
        {
            // Add row DOM (with species selector and stoichiometry)
            var reactantProductRowDOM = "<tr> \
<td> \
<button type=\"button\" class=\"btn btn-default delete\"> \
<i class=\"icon-remove\"></i></span> \
</button> \
</td> \
<td> \
<select class=\"species\"></select> \
</td> \
<td> \
<input class=\"stoichiometry\"> \
</td> \
</tr>";

            var reactionEditor = this.$el.find( "#reactionEditorDiv" );

            var reactantAndProductSelectDiv = reactionEditor.find( '.reactantAndProductSelectDiv' );
            // Add in the reactant and product selector

            var reactantSelector = reactantAndProductSelectDiv.find( '.reactantSelector' );

            var row = $( reactantProductRowDOM ).appendTo( reactantSelector.find( '.reactantsTableBody' ) );
            
            var deleteButton = row.find( '.delete' );
            var select = row.find( '.species' );
            var stoichiometry = row.find( '.stoichiometry' );

            // When clicked, this button removes the element
            deleteButton.on('click', _.partial(function(reactantHandle, reactionHandle, model, doms, event) {
                delete model.reactions[reactionHandle].reactants[reactantHandle];

                for(var i in doms)
                {
                    doms[i].remove();
                } 
            }, reactantHandle, reactionHandle, model, [deleteButton, select, stoichiometry, row]));
            
            // Add each item to select DOM storing the species names in the vals
            for(specie in model.species) {
                var option = $( "<option value=\"" + specie + "\">" + model.species[specie].name + " </option>").appendTo( select );

                if(model.reactions[reactionHandle].reactants[reactantHandle].name == specie)
                {
                    option.prop('selected', true);
                }
            }

            stoichiometry.val(model.reactions[reactionHandle].reactants[reactantHandle].stoichiometry);

            // Add on select change DOM calling handleReactantSelectChange
            select.on('change', _.bind(_.partial(this.handleReactantSelectChange, reactantHandle, reactionHandle, model), this));

            // Add on stoichiometry change DOM calling handleReactantStoichiometryChange
            stoichiometry.on('change', _.bind(_.partial(this.handleReactantStoichiometryChange, reactantHandle, reactionHandle, model), this));
        },

        handleReactantSelectChange : function(reactantHandle, reactionHandle, model, event) {
            var val = $( event.target ).val().trim();
            
            var inuse = false;
            var names = [];
            for(var specie in model.species)
            {
                if(val == specie) //model.species[specie].name
                {
                    inuse = true;
                    break;
                }
            }
            
            // Validate input (if the species doesn't exist, can't select it)
            if(!inuse)
            {
                this.reactionsMsg(false, "Species does not exist. This is an internal error. Try reloading the page");
            }
            // Change the value!
            else
            {
                model.reactions[reactionHandle].reactants[reactantHandle].name = val;
                
                this.reactionsMsg(true, "Reactant " + model.species[val].name + " selected");

                this.saveModel();
            }
        },

        handleReactantStoichiometryChange : function(reactantHandle, reactionHandle, model, event) {
            var val = $( event.target ).val().trim();

            var name = model.reactions[reactionHandle].reactants[reactantHandle].name;
            
            // Validate input
            if(isNaN(val))
            {
                this.reactionsMsg(false, "Stoichiometry not understood");
            }
            // Make sure it's not in use
            else if(!/^[0-9]+$/.test(val))
            {
                this.reactionsMsg(false, "Input value for stoichiometry must be an integer");
            }
            // Change the value!
            else
            {
                model.reactions[reactionHandle].reactants[reactantHandle].stoichiometry = parseFloat(val);
                
                this.reactionsMsg(true, "Stoichiometry set to " + parseFloat(val).toString());

                this.saveModel();
            }
        },

        handleReactionRateChange : function(reactionHandle, model, event) {
            var val = $( event.target ).val().trim();

            var name = model.reactions[reactionHandle].name;

            // Validate input
            if(isNaN(val))
            {
                this.reactionsMsg(false, "Input value for reaction " + name + " not understood");
            }
            // Make sure it's a real >= 0
            else if(parseFloat(val) < 0)
            {
                this.reactionsMsg(false, "Input value for reaction " + name + " must be positive");
            }
            // Change the value!
            else
            {
                model.reactions[reactionHandle].rate = parseFloat(val);
                
                this.reactionsMsg(true, "Reaction " + name + " rate set to " + parseFloat(val).toString());

                this.saveModel();
            }
        },

        addProductDom : function(productHandle, reactionHandle, model)
        {
            // Add row DOM (with species selector and stoichiometry)
            var reactantProductRowDOM = "<tr> \
<td> \
<button type=\"button\" class=\"btn btn-default delete\"> \
<i class=\"icon-remove\"></i> \
</button> \
</td> \
<td> \
<select class=\"species\"></select> \
</td> \
<td> \
<input class=\"stoichiometry\"> \
</td> \
</tr>";

            var reactionEditor = this.$el.find( "#reactionEditorDiv" );

            var reactantAndProductSelectDiv = reactionEditor.find( '.reactantAndProductSelectDiv' );
            // Add in the reactant and product selector

            var productSelector = reactantAndProductSelectDiv.find( '.productSelector' );

            var row = $( reactantProductRowDOM ).appendTo( productSelector.find( '.productsTableBody' ) );
            
            var deleteButton = row.find( '.delete' );
            var select = row.find( '.species' );
            var stoichiometry = row.find( '.stoichiometry' );

            // When clicked, this button removes the element
            deleteButton.on('click', _.partial(function(productHandle, reactionHandle, model, doms, event) {
                delete model.reactions[reactionHandle].products[productHandle];

                for(var i in doms)
                {
                    doms[i].remove();
                } 
            }, productHandle, reactionHandle, model, [deleteButton, select, stoichiometry, row]));
            
            // Add each item to select DOM storing the species names in the vals
            for(specie in model.species) {
                var option = $( "<option value=\"" + specie + "\">" + model.species[specie].name + " </option>").appendTo( select );

                if(model.reactions[reactionHandle].products[productHandle].name == specie)
                {
                    option.prop('selected', true);
                }
            }

            stoichiometry.val(model.reactions[reactionHandle].products[productHandle].stoichiometry);

            // Add on select change DOM calling handleReactantSelectChange
            select.on('change', _.bind(_.partial(this.handleProductSelectChange, productHandle, reactionHandle, model), this));

            // Add on stoichiometry change DOM calling handleReactantStoichiometryChange
            stoichiometry.on('change', _.bind(_.partial(this.handleProductStoichiometryChange, productHandle, reactionHandle, model), this));
        },

        handleProductSelectChange : function(productHandle, reactionHandle, model, handle) {
            var val = $( event.target ).val().trim();
            
            var inuse = false;
            var names = [];
            for(var specie in model.species)
            {
                if(val == specie) //model.species[specie].name
                {
                    inuse = true;
                    break;
                }
            }
            
            // Validate input (if the species doesn't exist, can't select it)
            if(!inuse)
            {
                this.reactionsMsg(false, "Species does not exist. This is an internal error. Try reloading the page");
            }
            // Change the value!
            else
            {
                model.reactions[reactionHandle].products[productHandle].name = val;
                
                this.reactionsMsg(true, "Product " + model.species[val].name + " selected");

                this.saveModel();
            }
        },

        handleProductStoichiometryChange : function(productHandle, reactionHandle, model, handle) {
            var val = $( event.target ).val().trim();

            var name = model.reactions[reactionHandle].products[productHandle].name;
            
            // Validate input
            if(isNaN(val))
            {
                this.reactionsMsg(false, "Stoichiometry of species " + name + " not understood");
            }
            // Make sure it's not in use
            else if(!/^[0-9]+$/.test(val))
            {
                this.reactionsMsg(false, "Input value for stoichiometry of product " + name + " must be an integer");
            }
            // Change the value!
            else
            {
                model.reactions[reactionHandle].products[productHandle].stoichiometry = parseFloat(val);
                
                this.reactionsMsg(true, "Stoichiometry of product " + name + " set to " + parseFloat(val).toString());

                this.saveModel();
            }
        },

        addReaction : function()
        {
            var newHandle = getNewMemberName(this.model.attributes.reactions, 'reaction');
            
            this.model.attributes.reactions[newHandle] = { name : newHandle,
                                                       reactants : {},
                                                       products : {},
                                                       type : 'massaction' };
            
            this.addReactionsDom(newHandle, this.model.attributes);
        },

        addExtraDom : function(extraHandle, reactionHandle, model)
        {
            // Add row DOM (with species selector and stoichiometry)
            var extraRowDOM = "<tr> \
<td> \
<button type=\"button\" class=\"btn btn-default delete\"> \
<i class=\"icon-remove\"></i> \
</button> \
</td> \
<td> \
<select class=\"interaction\"></select> \
</td> \
<td> \
<select class=\"species\"></select> \
</td> \
<td> \
<input class=\"rate\"> \
</td> \
</tr>";

            var reactionEditor = this.$el.find( "#reactionEditorDiv" );

            var row = $( extraRowDOM ).appendTo( reactionEditor.find( '.extraTableBody' ) );
            
            var deleteButton = row.find( '.delete' );
            var interactionSelect = row.find( '.interaction' );
            var select = row.find( '.species' );
            var rate = row.find( '.rate' );

            // When clicked, this button removes the element
            deleteButton.on('click', _.partial(function(extraHandle, reactionHandle, model, doms, event) {
                delete model.reactions[reactionHandle].extras[extraHandle];

                for(var i in doms)
                {
                    doms[i].remove();
                } 
            }, extraHandle, reactionHandle, model, [deleteButton, select, interactionSelect, rate, row]));
            
            // Add each item to select DOM storing the species names in the vals
            for(specie in model.species) {
                var option = $( "<option value=\"" + specie + "\">" + model.species[specie].name + " </option>").appendTo( select );

                if(model.reactions[reactionHandle].extras[extraHandle].name == specie)
                {
                    option.prop('selected', true);
                }
            }
            
            var option = $( "<option value=\"activation\">Activation</option>").appendTo( interactionSelect );

            if(model.reactions[reactionHandle].extras[extraHandle].type == "activation")
            {
                option.prop('selected', true);
            }

            option = $( "<option value=\"competativeInhibition\">Competative Inhibition</option>").appendTo( interactionSelect );

            if(model.reactions[reactionHandle].extras[extraHandle].type == "competativeInhibition")
            {
                option.prop('selected', true);
            }

            option = $( "<option value=\"uncompetativeInhibition\">Uncompetative Inhibition</option>").appendTo( interactionSelect );

            if(model.reactions[reactionHandle].extras[extraHandle].type == "uncompetativeInhibition")
            {
                option.prop('selected', true);
            }

            option = $( "<option value=\"noncompetativeInhibition\">Noncompetative Inhibition</option>").appendTo( interactionSelect );

            if(model.reactions[reactionHandle].extras[extraHandle].type == "noncompetativeInhibition")
            {
                option.prop('selected', true);
            }

            option = $( "<option value=\"extraSubstrate\">Extra Substrate</option>").appendTo( interactionSelect );

            if(model.reactions[reactionHandle].extras[extraHandle].type == "extraSubstrate")
            {
                option.prop('selected', true);
            }

            rate.val(model.reactions[reactionHandle].extras[extraHandle].rate);

            // Add on select change DOM calling handleReactantSelectChange
            interactionSelect.on('change', _.bind(_.partial(this.handleInteractionSelectChange, extraHandle, reactionHandle, model), this));

            // Add on select change DOM calling handleReactantSelectChange
            select.on('change', _.bind(_.partial(this.handleExtraSelectChange, extraHandle, reactionHandle, model), this));

            // Add on stoichiometry change DOM calling handleReactantStoichiometryChange
            rate.on('change', _.bind(_.partial(this.handleExtraRateChange, extraHandle, reactionHandle, model), this));

            this.updateMichaelisMentonPreview(reactionHandle, model);
        },

        handleMichaelisMentonReactantSelectChange : function(reactionHandle, model, event) {
            var val = $( event.target ).val().trim();
            
            var inuse = false;
            var names = [];
            for(var specie in model.species)
            {
                if(val == specie) //model.species[specie].name
                {
                    inuse = true;
                    break;
                }
            }

            if(val == '')
            {
                inuse = true;
            }
            
            // Validate input (if the species doesn't exist, can't select it)
            if(!inuse)
            {
                this.reactionsMsg(false, "Species does not exist. This is an internal error. Try reloading the page");
            }
            // Change the value!
            else
            {
                model.reactions[reactionHandle].reactant = val;

                var name;

                if(val == '')
                    name = 'null';
                else
                    name = model.species[val].name;

                this.reactionsMsg(true, "Reactant " + name + " selected");

                this.updateMichaelisMentonPreview(reactionHandle, model);

                this.saveModel();
            }
        },

        handleMichaelisMentonProductSelectChange : function(reactionHandle, model, event) {
            var val = $( event.target ).val().trim();
            
            var inuse = false;
            var names = [];
            for(var specie in model.species)
            {
                if(val == specie) //model.species[specie].name
                {
                    inuse = true;
                    break;
                }
            }

            if(val == '')
            {
                inuse = true;
            }
            
            // Validate input (if the species doesn't exist, can't select it)
            if(!inuse)
            {
                this.reactionsMsg(false, "Species does not exist. This is an internal error. Try reloading the page");
            }
            // Change the value!
            else
            {
                model.reactions[reactionHandle].product = val;

                var name;

                if(val == '')
                    name = 'null';
                else
                    name = model.species[val].name;

                this.reactionsMsg(true, "Product " + name + " selected");

                this.updateMichaelisMentonPreview(reactionHandle, model);

                this.saveModel();
            }
        },

        handleExtraSelectChange : function(extraHandle, reactionHandle, model, event) {
            var val = $( event.target ).val().trim();
            
            var inuse = false;
            var names = [];
            for(var specie in model.species)
            {
                if(val == specie) //model.species[specie].name
                {
                    inuse = true;
                    break;
                }
            }

            if(val == '')
            {
                inuse = true;
            }
            
            // Validate input (if the species doesn't exist, can't select it)
            if(!inuse)
            {
                this.reactionsMsg(false, "Species does not exist. This is an internal error. Try reloading the page");
            }
            // Change the value!
            else
            {
                model.reactions[reactionHandle].extras[extraHandle].name = val;

                var name = model.species[val].name;

                this.reactionsMsg(true, "Species " + name + " selected");

                this.updateMichaelisMentonPreview(reactionHandle, model);

                this.saveModel();
            }
        },

        handleInteractionSelectChange : function(extraHandle, reactionHandle, model, event) {
            var val = $( event.target ).val().trim();

            var interaction;

            if(val == 'activation')
            {
                interaction = 'activation';
            }
            else if(val == 'competativeInhibition')
            {
                interaction = 'competative inhibition';
            }
            else if(val == 'uncompetativeInhibition')
            {
                interaction = 'uncompetative inhibition';
            }
            else if(val == 'noncompetativeInhibition')
            {
                interaction = 'noncompetative inhibition';
            }
            else if(val == 'extraSubstrate')
            {
                interaction = 'extra substrate';
            }
            else
            {
                this.reactionsMsg(false, "Interaction type not understood");
                return;
            }
            
            model.reactions[reactionHandle].extras[extraHandle].type = val;
            this.reactionsMsg(true, "Interaction type set to " + interaction);

            this.updateMichaelisMentonPreview(reactionHandle, model);

            this.saveModel();
        },

        handleExtraAddButton : function(reactionHandle, model, event) {
            var extraHandle = getNewMemberName(model.reactions[reactionHandle].extras, 'e');

            // If the next 6 lines seem weird, it's cause they are
            //    extract any valid species name
            var reactantName = null, productName = null;

            for(var specie in model.species)
            {
                if(reactantName == null)
                {
                    reactantName = specie;
                }
                else
                {
                    productName = specie;
                    break;
                }
            }
            
            model.reactions[reactionHandle].extras[extraHandle] = { name : reactantName, type : 'activation', rate : 0 };
           
            this.addExtraDom(extraHandle, reactionHandle, model);

            this.updateMichaelisMentonPreview(reactionHandle, model);

            this.saveModel();
        },

        handleVRateChange : function(reactionHandle, model, event) {
            var val = $( event.target ).val().trim();

            var name = model.reactions[reactionHandle].name;

            // Validate input
            if(isNaN(val))
            {
                this.reactionsMsg(false, "v not understood (must be a positive, real number)");
            }
            // Make sure it's a real >= 0
            else if(parseFloat(val) < 0)
            {
                this.reactionsMsg(false, "v must be positive");
            }
            // Change the value!
            else
            {
                model.reactions[reactionHandle].vRate = parseFloat(val);
                
                this.reactionsMsg(true, "v rate set to " + parseFloat(val).toString());

                this.updateMichaelisMentonPreview(reactionHandle, model);

                this.saveModel();
            }
        },

        handleKmRateChange : function(reactionHandle, model, event) {
            var val = $( event.target ).val().trim();

            var name = model.reactions[reactionHandle].name;

            // Validate input
            if(isNaN(val))
            {
                this.reactionsMsg(false, "Km not understood (must be a positive, real number)");
            }
            // Make sure it's a real >= 0
            else if(parseFloat(val) < 0)
            {
                this.reactionsMsg(false, "Km must be positive");
            }
            // Change the value!
            else
            {
                model.reactions[reactionHandle].KmRate = parseFloat(val);
                
                this.reactionsMsg(true, "Km set to " + parseFloat(val).toString());

                this.updateMichaelisMentonPreview(reactionHandle, model);

                this.saveModel();
            }
        },

        handleExtraRateChange : function(extraHandle, reactionHandle, model, event) {
            var val = $( event.target ).val().trim();

            var name = model.reactions[reactionHandle].name;

            // Validate input
            if(isNaN(val))
            {
                this.reactionsMsg(false, "Extra interaction rate not understood (must be a positive, real number)");
            }
            // Make sure it's a real >= 0
            else if(parseFloat(val) < 0)
            {
                this.reactionsMsg(false, "Extra interaction rate must be positive");
            }
            // Change the value!
            else
            {
                model.reactions[reactionHandle].extras[extraHandle].rate = parseFloat(val);
                
                this.reactionsMsg(true, "Extra interaction rate for reaction " + name + " set to " + parseFloat(val).toString());

                this.updateMichaelisMentonPreview(reactionHandle, model);

                this.saveModel();
            }
        },

        updateMichaelisMentonPreview : function(reactionHandle, model)
        {
            var lat = '';

            var substrates = [];
            var reaction = model.reactions[reactionHandle];

            var num = '\\frac{v}{\\Omega}'

            if(reaction.reactant.length > 0)
                num = num + model.species[reaction.reactant].name;

            var actNum = ''
            var actDen = ''
            var competativeDen = ''
            var uncompetativeDen = ''
            var noncompetative = ''

            var extraSubstrateDen = ''

            for(var extraK in reaction.extras)
            {
                var extra = reaction.extras[extraK];

                if(extra.type == 'activation')
                {
                    if(actDen != '')
                        actDen += ' + ';

                    actDen += '\\frac{' + model.species[extra.name].name + '}{\\Omega K_{' + model.species[extra.name].name + ' }}';

                    actNum += '\\frac{' + model.species[extra.name].name + '}{\\Omega}'
                }

                if(extra.type == 'competativeInhibition')
                {
                    if(competativeDen != '')
                        competativeDen += ' + ';

                    competativeDen += '\\frac{' + model.species[extra.name].name + '}{\\Omega K_{' + model.species[extra.name].name + ' }}';
                }

                if(extra.type == 'uncompetativeInhibition')
                {
                    if(uncompetativeDen != '')
                        uncompetativeDen += ' + ';

                    uncompetativeDen += '\\frac{' + model.species[extra.name].name + '}{\\Omega K_{' + model.species[extra.name].name + ' }}';
                }

                if(extra.type == 'noncompetativeInhibition')
                {
                    noncompetative += '\\frac{1}{1 + \\frac{' + model.species[extra.name].name + '}{\\Omega K_{' + model.species[extra.name].name + ' }}}';
                }
            }

            for(var extraK in reaction.extras)
            {
                var extra = reaction.extras[extraK];

                if(extra.type == 'uncompetativeInhibition')
                {
                    if(extraSubstrateDen != '')
                        extraSubstrateDen += ' + ';

                    extraSubstrateDen += '\\frac{' + model.species[extra.name].name + '}{\\Omega K_{' + model.species[extra.name].name + ' }}\\left(' + uncompetativeDen + '\\right)';
                }
            }

            if(_.keys(reaction.extras).length > 0)
            {
                if(actDen != '')
                    actDen = ' + ' + actDen;

                if(extraSubstrateDen != '')
                    extraSubstrateDen = ' + ' + extraSubstrateDen;

                if(competativeDen != '')
                    competativeDen = ' + ' + competativeDen;

                if(noncompetative != '')
                    noncompetative = '\\left(' + noncompetative + '\\right)';

                $( '#preview' ).html('$$\\frac{' + num + '}{1 ' + actDen + extraSubstrateDen + competativeDen + '} ' + noncompetative + '$$');
            }
            else
            {
                $( '#preview' ).html('$$empty$$');
            }
            var math = document.getElementById("preview");
            MathJax.Hub.Queue(["Typeset",MathJax.Hub, math]);
        },

        // This render is a little different than others I write
        //
        // Generally it should only be called once when the page is loaded
        // It is the responsibility of all the little elements to add event handlers and such to keep themselves updated
        render : function()
        {
            // Convert XML to custom internal format
            var model = this.model.attributes;

            for(var specieName in model.species)
            {
                //var newHandle = getNewMemberName(model.species, 'specie');
                
                //model.species[newHandle] = { name : newHandle,
                //                             initialCondition : 0 };

                this.addSpeciesDom(specieName, model);
            }

            for(var reactionName in model.reactions)
            {
                //var newHandle = getNewMemberName(model.species, 'specie');
                
                //model.species[newHandle] = { name : newHandle,
                //                             initialCondition : 0 };

                this.addReactionsDom(reactionName, model);
            }
        }
    }
);

$( document ).ready( function() {
    var id = $.url().param("id");

    var control = new ModelEditor.Controller( );
    var selector = new ModelEditor.Selector( { controller : control } );
});
