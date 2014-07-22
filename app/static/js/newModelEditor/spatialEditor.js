var ModelEditor = ModelEditor || {}

var modelData = {
    species : { species0 : { name : "s1", D : 1000 }, species1 : { name : "s2", D : 51202 } },
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
    subdomains : { 1 : { name : "region1", reactions : ['reaction0', 'reaction1'] } , 2 : { name : "region3", reactions : [ 'reaction0' ] } },
    initialConditions : { ic0 : { type : "point", x : 5.0, y : 10.0, z : 1.0, count : 5000 }, ic1 : { type : "concentration", subdomains : [1, 2], concentration : 1.0 }, ic2 : { type : "population", subdomains : [2], population : 100 }}
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

ModelEditor.Controller = Backbone.View.extend(
    {
        events: {
            //"click #addSpeciesButton"  : "addSpecies",
            //"click #addReactionButton" : "addReaction",
            //"click #addMichaelisMentonReactionButton" : "addMichaelisMentonReaction"
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

            // Draw a screen so folks have something to see
            this.render();

            // Go off and fetch those models and queue up a render on completion
            //this.models = new stochkit.ModelCollection();

            // Go get the csvFiles we have hosted
            //this.initialDataFiles = new fileserver.FileList( [], { key : 'stochOptimInitialData' } );

            $( '.initialData' ).hide();
            $( '.trajectories' ).hide();

            // When finished, queue up another render
            //this.models.fetch( { success : _.bind(this.render, this) } );

            //this.initialDataFiles.fetch( { success : _.bind(this.render, this) } );
        },

        addReactionSubdomainSelectDom : function(model)
        {
            var model = this.attributes.m;

            // Build the header for reaction/species selection table
            var element = $( "<th>" ).appendTo( this.$el.find( ".reactionSubdomainSelectTableHeader" ) );
            element.html("Subdomains");
            
            for(var subdomainKey in model.subdomains)
            {
                var element = $( "<th>" ).appendTo( this.$el.find( ".reactionSubdomainSelectTableHeader" ) );

                element.html(model.subdomains[subdomainKey].name);
            }

            // Build the body for the reaction/species selection table
            for(var subdomainKey in model.subdomains)
            {
                var row = $( "<tr>" ).appendTo( this.$el.find( ".reactionSubdomainSelectTableBody" ) );
                
                var leftCol = $( "<td>" ).appendTo( row );
                
                leftCol.html(model.subdomains[subdomainKey].name);
                
                for(var reactionKey in model.reactions)
                {
                    var col = $( "<td>" ).appendTo( row );

                    var checkbox = $( "<input type=\"checkbox\">" ).appendTo( col );

                    if(_.indexOf(model.subdomains[subdomainKey].reactions, reactionKey) >= 0)
                    {
                        checkbox.prop('checked', true);
                    }

                    //checkbox.on("change", _.bind(_.partial(this.handleReactionSubdomainSelect, specieKey, regionKey), this));
                }
            }

            var initialConditionsTableBodyTemplate = "<tr> \
<td> \
<button type=\"button\" class=\"btn btn-default btn-lg\" class=\"addInitialConditionsButton\"> \
<span class=\"glyphicon glyphicon-remove\"></span> \
</button> \
</td> \
<td><select class=\"type\"></select></td> \
<td><select class=\"species\"></select></td> \
<td class=\"custom\"></td> \
</tr>";

            var possibleTypes = ["point", "concentration", "population"];

            // Add in a row for every initial condition
            for(var initialConditionKey in model.initialConditions)
            {
                var row = $( initialConditionsTableBodyTemplate ).appendTo( this.$el.find( ".initialTableBody" ) );

                var typeSelect = row.find( '.type' );
                var speciesSelect = row.find( '.species' );
                var custom = row.find( '.custom' );

                // Event handle for delete
                for(var i in possibleTypes)
                {
                    var option = $( '<option value="' + possibleTypes[i] + '">' + possibleTypes[i] + '</option>' ).appendTo( typeSelect );

                    if(model.initialConditions[initialConditionKey].type == possibleTypes[i])
                    {
                        option.prop('selected', true);
                    }
                }

                // Write in species in drop down menu
                for(var species in model.species)
                {
                    var option = $( '<option value="' + species + '">' + model.species[species].name + '</option>' ).appendTo( speciesSelect );
                }

                // Write in the custom stuff
                if(model.initialConditions[initialConditionKey].type == "point")
                {
                    var extraOptionsTemplate = '<table class="table"> \
<thead> \
<tr> \
<td>Count</td><td>X</td><td>Y</td><td>Z</td> \
</tr> \
</thead> \
<tbody> \
<tr> \
<td> \
<input class="count" val="0"/> \
</td> \
<td> \
<input class="X" val="0" /> \
</td> \
<td> \
<input class="Y" val="0" /> \
</td> \
<td> \
<input class="Z" val="0" /> \
</td> \
</tr> \
</tbody> \
</table>';

                    custom.html( extraOptionsTemplate );

                    var xBox = custom.find( '.X' );
                    var yBox = custom.find( '.Y' );
                    var zBox = custom.find( '.Z' );

                    xBox.val(model.initialConditions[initialConditionKey].x);
                    yBox.val(model.initialConditions[initialConditionKey].y);
                    zBox.val(model.initialConditions[initialConditionKey].z);

                    var countBox = custom.find( '.count' );

                    countBox.val(model.initialConditions[initialConditionKey].count);
                }
                else if(model.initialConditions[initialConditionKey].type == "concentration")
                {
                    //ic1 : { type : "concentration", subdomain : 1, concentration : 1.0 }
                    var extraOptionsTemplate = '<div class="row"> \
<div class="col-md-3"> \
<table class="table"> \
<thead> \
<tr> \
<td> \
Subdomains \
</td> \
</tr> \
</thead> \
<tbody class="subdomains"> \
</tbody> \
</table> \
<button type="button" class="btn btn-default btn-md" class="addSubdomainsButton"> \
<span class="glyphicon glyphicon-plus"></span> Add Subdomain \
</button> \
</div> \
<div class="col-md-2"> \
<table class="table"> \
<thead> \
<tr> \
<td> \
Concentration \
</td> \
</tr> \
</thead> \
<tbody> \
<tr> \
<td> \
<input class="concentration" val="0.0" /> \
</td> \
</tr> \
</tbody> \
</table> \
</div> \
</div>';

//'<tr>
//<td>
//'
                    custom.html(extraOptionsTemplate);

                    var subdomainsTableBody = custom.find( '.subdomains' );
                    var concentrationBox = custom.find( '.concentration' );

                    for(var i in model.initialConditions[initialConditionKey].subdomains)
                    {
                        var select = $( '<tr><td><select></select></td></tr>' ).appendTo( subdomainsTableBody ).find( 'select' );

                        for(var subdomainKey in model.subdomains)
                        {
                            var subdomainCheckboxTemplate = '<option val="' + subdomainKey + '">' + model.subdomains[subdomainKey].name + '</option>';

                            var menuItem = $( subdomainCheckboxTemplate ).appendTo( select );

                            if(model.initialConditions[initialConditionKey].subdomains[i] == subdomainKey)
                            {
                                menuItem.prop('selected', true);
                            }
                        }
                    }

                    concentrationBox.val(model.initialConditions[initialConditionKey].concentration);
                }
                else if(model.initialConditions[initialConditionKey].type == "population")
                {
                    //ic2 : { type : "population", subdomain : 2, population : 100 }
                    var extraOptionsTemplate = '<div class="row"> \
<div class="col-md-3"> \
<table class="table"> \
<thead> \
<tr> \
<td> \
Subdomains \
</td> \
</tr> \
</thead> \
<tbody class="subdomains"> \
</tbody> \
</table> \
<button type="button" class="btn btn-default btn-md" class="addSubdomainsButton"> \
<span class="glyphicon glyphicon-plus"></span> Add Subdomain \
</button> \
</div> \
<div class="col-md-2"> \
<table class="table"> \
<thead> \
<tr> \
<td> \
Population \
</td> \
</tr> \
</thead> \
<tbody> \
<tr> \
<td> \
<input class="population" val="0" /> \
</td> \
</tr> \
</tbody> \
</table> \
</div> \
</div>';

                    custom.html(extraOptionsTemplate);

                    var subdomainsTableBody = custom.find( '.subdomains' );
                    var populationBox = custom.find( '.population' );

                    for(var i in model.initialConditions[initialConditionKey].subdomains)
                    {
                        var select = $( '<tr><td><select></select></td></tr>' ).appendTo( subdomainsTableBody ).find( 'select' );

                        for(var subdomainKey in model.subdomains)
                        {
                            var subdomainCheckboxTemplate = '<option val="' + subdomainKey + '">' + model.subdomains[subdomainKey].name + '</option>';

                            var menuItem = $( subdomainCheckboxTemplate ).appendTo( select );

                            if(model.initialConditions[initialConditionKey].subdomains[i] == subdomainKey)
                            {
                                menuItem.prop('selected', true);
                            }
                        }
                    }

                    populationBox.val(model.initialConditions[initialConditionKey].population);
                }
            }
        },

        // This render should only be called once. Calling multiple times might mess up some of
        //   the page state information
        render : function()
        {
            var model = this.attributes.m;

            this.addReactionSubdomainSelectDom(model);
        }
    }
);

var run = function()
{
    
    // This is where most of the miscellaneous junk should go
    var control = new ModelEditor.Controller( { m : modelData } );
    
    // Get the ball rolling
    //modelCollection.fetch({ success : function(modelSelect) {
    //    $( '#modelSelect' ).trigger('change');
    //} });
}

$( document ).ready( function() {
    //loadTemplate("speciesEditorTemplate", "/model/speciesEditor.html");
    //loadTemplate("parameterEditorTemplate", "/model/parameterEditor.html");
    //loadTemplate("reactionEditorTemplate", "/model/reactionEditor.html");

    run();
});
