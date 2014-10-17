var stochkit = stochkit || {}
stochkit.PrettyPrint = {}

var XML = function(el)
{
    return $($.parseXML(el)).children();
}

stochkit.Model = Backbone.Model.extend( {
    //Expects attributes to have a type varibleo
    initialize: function(attributes) {
    }
});

stochkit.PrettyPrint.Reaction = function(reaction) {
    var reactants = reaction.find('Reactants').children();
    var products = reaction.find('Products').children();
    
    var expressionString = '';
    var propensityString = '';
    for(var j = 0; j < reactants.length; j++) {
        var s = reactants.eq(j).attr('stoichiometry');
        var id = reactants.eq(j).attr('id');

        if(s == '1') {
            expressionString += id;
        } else {
            expressionString += s + '*' + id;
        }

        propensityString += '*';
        if(s == '1')
        {
            propensityString += reactants.eq(j).attr('id');
        } else {
            propensityString += '(' + reactants.eq(j).attr('id') + '^' + s + ')';
        }
        
        if(j != reactants.length - 1)
        {
            expressionString += '+';
        }
    }

    if(expressionString == '')
    {
	expressionString += "null";
    }
    
    expressionString += '=>'

    for(var j = 0; j < products.length; j++) {
        var s = products.eq(j).attr('stoichiometry');
        var id = products.eq(j).attr('id');

        if(s == '1') {
            expressionString += id;
        } else {
            expressionString += s + '*' + id;
        }
        
        if(j != products.length - 1)
        {
            expressionString += '+';
        }
    }

    if(products.length == 0) {
        expressionString += " null ";
    }

    var type = reaction.find('Type').text();

    if(type.toLowerCase() == 'mass-action')
    {
        propensityString = reaction.find('Rate').text() + propensityString;
    }
    else
    {
        propensityString = reaction.find('PropensityFunction').text();
    }

    var prettyReaction = {}

    prettyReaction.expression = expressionString;
    prettyReaction.propensity = propensityString;

    return prettyReaction;
};

// Initializing one of these gets you access to the full models
stochkit.ModelCollection = Backbone.Collection.extend( {
    url: "/models/list",
    model: stochkit.Model
});

// Initializing these gets you access to the models - the actual model xml file. All you get are
//   the things 
//stochkit.ModelInfoCollection = Backbone.Collection.extend( {
//    url: "/models/info",
//    model: stochkit.Model
//});
