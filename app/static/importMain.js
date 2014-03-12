var Import = Import || {}

Import.ArchiveSelect = Backbone.View.extend(
    {
        initialize: function(options)
        {
            this.$el = $( "#archiveSelect" );

            /*this.$el.change( function(event) {
                $( event.target ).find( "option:selected" ).trigger('select');
            });*/

	    this.optionTemp = _.template('<tr> \
<td><a href="javascript:preventDefault();">Delete</a></td><td><input type="radio" name="archive"></td><td><%= zipFile %></td>\
</tr>');

            this.state = { selected : 0 };
            
            this.$el.hide();
        },

        attach: function(data)
        {
            this.data = data;

            this.state = { selected : 0 };

            this.render();

            this.trigger('select', data[0]);
        },

        render: function()
        {
            this.$el.empty();

            if(_.has(this, 'data')) {
                if(this.data.length > 0)
                {
                    $( "#archiveSelectDiv" ).show();
                }

                for(var i = 0; i < this.data.length; i++)
                {
                    var newOption = $( this.optionTemp( this.data[i]) ).appendTo( this.$el );

                    newOption.find('input').on('click', _.partial( function(data, view) {
                        view.trigger('select', data);
                    }, this.data[i], this));

                    newOption.find('a').click( _.partial(function(id, event) {
                        event.preventDefault();

                        $.post("/import?reqType=delJob&id=" + id,
                               success = function(data)
                               {
                                   location.reload();
                               });
                    }, this.data[i].id));
                }
            }

            this.$el.find('input').eq(0).click();

            this.$el.show();

            return this;
        }
    });

Import.ImportTable = Backbone.View.extend(
    {
        initialize: function(options)
        {
            this.$el = $( "#importTable" );

	    this.modelRowTemplate = _.template('<tr>\
<td><input type="checkbox" /></td>\
<td><%= name %></td>\
<td><%= units %></td>\
</tr>');

	    this.rowTemplate = _.template('<tr>\
<td><input type="checkbox" /></td>\
<td><%= name %></td>\
<td><%= exec_type %></td>\
</tr>');

	    this.sensitivityTemplate = _.template('<tr>\
<td><input type="checkbox" /></td>\
<td><%= jobName %></td>\
</tr>');

            this.mc = this.$el.find( '#modelContainer' );
            this.sjc = this.$el.find( '#stochkitJobContainer' );
            this.snc = this.$el.find( '#sensitivityJobContainer' );

            this.state = { id : undefined, selections : { mc : {}, sjc : {}, snc : {} } };
            
            this.$el.hide();
        },

        attach: function(archiveSelect)
        {
            this.archiveSelect = archiveSelect;

            this.listenTo(archiveSelect, 'select', this.render);

            this.render();
        },

        render: function(data)
        {
            this.mc.empty();
            this.sjc.empty();
            this.snc.empty();

            if(typeof data != 'undefined') {
                this.state.id = data.id;
                this.data = data;

                $( ".modelContainerTr" ).hide();
                for(var name in this.data.headers.models) {
                    $( ".modelContainerTr" ).show();
                    console.log(name)
                    var model = this.data.headers.models[name];

                    var html = this.modelRowTemplate(model);

                    var boxparam = $( html ).appendTo( this.mc );

                    boxparam.find('input').change( _.partial(function(state, id, event) {
                        state[id] = $( event.target ).prop( 'checked' );
                    }, this.state.selections.mc, name) );
                }

                $( ".stochkitContainerTr" ).hide();
                for(var name in this.data.headers.stochkitJobs) {
                    $( ".stochkitContainerTr" ).show();
                    var job = this.data.headers.stochkitJobs[name];

                    var html = this.rowTemplate(job);

                    var boxparam = $( html ).appendTo( this.sjc );

                    boxparam.find('input').change( _.partial(function(state, id, event) {
                        state[id] = $( event.target ).prop( 'checked' );
                    }, this.state.selections.sjc, name) );
                }

                $( ".sensitivityContainerTr" ).hide();
                for(var name in this.data.headers.sensitivityJobs) {
                    $( ".sensitivityContainerTr" ).show();
                    var job = this.data.headers.sensitivityJobs[name];

                    var html = this.sensitivityTemplate(job);

                    var boxparam = $( html ).appendTo( this.snc );

                    boxparam.find('input').change( _.partial(function(state, id, event) {
                        state[id] = $( event.target ).prop( 'checked' );
                    }, this.state.selections.snc, name) );
                }
            }

            this.$el.find('input').prop('checked', true).trigger('change');

            this.$el.show();

            return this;
        }
    });

$( document ).ready( function() {
    //loadTemplate("speciesEditorTemplate", "/model/speciesEditor.html");
    //loadTemplate("parameterEditorTemplate", "/model/parameterEditor.html");
    //loadTemplate("reactionEditorTemplate", "/model/reactionEditor.html");

    waitForTemplates(run);
});

var updateMsg = function(data)
{
    $( "#msg" ).html(data.msg);
    if(data.status)
        $( "#msg" ).css('color', 'green');
    else
        $( "#msg" ).css('color', 'red');
    $( "#msg" ).show();
};

var progressbar = _.template('<span><%= name %> :<div class="progress"> \
<div class="bar" style="width:0%;"> \
                       </div> \
</div> \
</span>');

var progressHandle = undefined;

var updateImportInfo = function(archiveSelect) {
    $.ajax( { type : "POST",
              url : "/import",
              data : { reqType : "importInfo" },
              success : _.partial(function(archiveSelect, data) {
                  archiveSelect.attach(data);
              }, archiveSelect),
              error: function(data)
              {
                  console.log("do I get called?");
              },
              dataType : 'json'
            });
}

var run = function()
{
    var archiveSelect = new Import.ArchiveSelect();
    var importTable = new Import.ImportTable();

    importTable.attach(archiveSelect);

    updateImportInfo(archiveSelect);

    updateImportInfo = _.partial( updateImportInfo, archiveSelect );

    $('#fileupload').fileupload({
        url: '/import',
        dataType: 'json',
        send: function (e, data) {
            names = "";

            for(var i in data.files)
            {
                names += data.files[i].name + " ";
            }

            progressHandle = $( progressbar({ name : names }) ).appendTo( "#progresses" );
        },
        done: function (e, data) {
            $.each(data.result, function (index, file) {
                console.log(file.name);
            });

            progressHandle.remove();

            updateImportInfo();
        },
        progressall: function (e, data) {
            var progress = parseInt(data.loaded / data.total * 100, 10);
            progressHandle.find('.bar' ).css('width', progress + '%');
            progressHandle.find('.bar' ).text(progress + '%');
        },
        error : function(data) {
            console.log('error');
        }
    }).prop('disabled', !$.support.fileInput)
        .parent().addClass($.support.fileInput ? undefined : 'disabled');

    $( "#export" ).click( function(e) {
        updateMsg( { status : true,
                     msg : "Submitting export job..." } );
        e.preventDefault();
        // Get all the names of cloud jobs for which the user wants to pull data from S3
        var stochKitJobsToExport = [];
        var checkboxes = document.getElementsByName('select_stochkit_job');
        for (var i = 0; i < checkboxes.length; i++)
        {
            if (checkboxes[i].checked) {
                stochKitJobsToExport.push(checkboxes[i].value);
            }
        }
        var sensitivityJobsToExport = [];
        checkboxes = document.getElementsByName('select_sensitivity_job');
        for (var i = 0; i < checkboxes.length; i++)
        {
            if (checkboxes[i].checked) {
                sensitivityJobsToExport.push(checkboxes[i].value);
            }
        }
        var ajaxData = {
            reqType : "backup",
            globalOp : $( "#globalOp" ).prop('checked'),
            stochKitJobs: stochKitJobsToExport,
            sensitivityJobs: sensitivityJobsToExport
        };
        $.ajax( { type : "POST",
                  url : "/export",
                  data : JSON.stringify(ajaxData),
                  success : function(data) {
                      updateMsg(data);
                      window.location = "/status";
                  },
                  error: function(data)
                  {
                      console.log("do I get called?");
                  },
                  dataType : 'json'
                });
    });

    $( "#import" ).click( function() {
        updateMsg( { status : true,
                     msg : "Importing models..." } );
        $.ajax( { type : "POST",
                  url : "/import",
                  data : { reqType : "doImport",
                           state : JSON.stringify(importTable.state),
                           globalOp : $( "#globalOp" ).prop('checked'),
                           overwriteType : $( "#overwriteType" ).val() },
                  success : updateMsg,
                  error: function(data)
                  {
                      console.log("do I get called?");
                  },
                  dataType : 'json'
                });
    });
}
