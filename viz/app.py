# kaldjian
# 9 june 2021
# dash visualization of GHA modeling results

try:
    __IPYTHON__
    STANDALONE = False
except NameError:
    STANDALONE = True

##############################################
##### jupyter dash setup + package imports ###
##############################################

if not STANDALONE:
    from jupyter_dash.comms import _send_jupyter_config_comm_request

    _send_jupyter_config_comm_request()

    from jupyter_dash import JupyterDash

    JupyterDash.infer_jupyter_proxy_config()

import pandas as pd
import geopandas as gpd

import plotly.express as px
import plotly.graph_objects as go

import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output

import json
import sys
import os
from textwrap import dedent as d

##########################
#### helper functions ####
##########################

# source: Yonatan Kiron on Stack Overflow
# https://stackoverflow.com/questions/30338430/humanize-numbers-with-python

def humanize_number(value, fraction_point=1):
    value = round(value)
    
    powers = [10 ** x for x in (12, 9, 6, 3, 0)]
    human_powers = ('T', 'B', 'M', 'K', '')
    is_negative = False
    
    if value == 0:
        return 0
    
    if not isinstance(value, float):
        value = float(value)
    if value < 0:
        is_negative = True
        value = abs(value)
    for i, p in enumerate(powers):
        if value >= p:
            return_value = str(round(value / (p / (10.0 ** fraction_point))) /
                               (10 ** fraction_point)) + human_powers[i]
            break
    if is_negative:
        return_value = "-" + return_value

    return return_value

def bold_before_colon(text):
    text = text.split(':')
    first_word = text.pop(0) + ':'
    
    return [html.B(first_word), text[0]]


######################
#### data imports ####
######################
    
with open('assets/landing.txt') as f:
    landing_text = f.readlines()
    
with open('assets/what_to_display.txt') as f:
    what_text = f.readlines()
    
with open('assets/how_to_display.txt') as f:
    how_text = f.readlines()


gdf = gpd.read_file('s3://hexa-blsq/data/geohealthaccess/cod-malaria/areas.geojson')

# formatting zone-level aggregates

gdf['fid'] = gdf.index
gdf['Pop_readable'] = gdf['PopTotal'].apply(lambda x: humanize_number(x))

gdf['centroid_lat'] = gdf['geometry'].centroid.y
gdf['centroid_lon'] = gdf['geometry'].centroid.x

cols = gdf.columns.to_list()
pct_cols = [c for c in cols if 'Percent' in c]
gdf[pct_cols] = gdf[pct_cols].apply(lambda x: 100*x)

# adding full zone and province names
# hfr = pd.read_csv('s3://hexa-cod-msp/data/iaso-edl/SNIS.csv')
# hfr = hfr[['parent 2', 'Ref Ext parent 2', 
#            'parent 3', 'Ref Ext parent 3']].drop_duplicates()
# hfr.rename(columns={'parent 2': 'zone_name',
#                     'Ref Ext parent 2': 'zone_id',
#                     'parent 3': 'prov_name',
#                     'Ref Ext parent 3': 'prov_id'}, 
#            inplace=True)

# gdf = gdf.merge(hfr, left_on='dhis2_code', right_on='zone_id', how='left')
# gdf.rename(columns={'name': 'zone_name_short',
#                     'zone_name': 'name'},
#            inplace=True)


########################
#### dash app setup ####
########################

token = open(".mapbox_token").read()
style = open(".mapbox_style").read()

if STANDALONE:
    app = dash.Dash(__name__)
else:
    app = JupyterDash(__name__)
    
# app component layout
app.layout = html.Div(id="app-main", children=[
    
    html.Div(id='modal', children =[  # modal div
        html.Div(id='modal-content', children = [  # content div
            html.Div([
                'This is the content of the modal',
            ]),
            html.Button('Close', id='modal-close-button')
        ],
            className='modal-content',
        ),
    ],
        className='modal',
        style={"display": "none"},
    ),
    
    html.Div(id='sidebar', children=[
        
        html.Div(id='ctrls-container', children=[
            html.Div(
                [
                    "Month",
                    dcc.Dropdown(
                        id='month', 
                        options=[
                            {'value': '202001', 'label': 'Jan 2020'},
                            {'value': '202002', 'label': 'Feb 2020'},
                            {'value': '202003', 'label': 'Mar 2020'},
                            {'value': '202004', 'label': 'Apr 2020'},
                            {'value': '202005', 'label': 'May 2020'},
                            {'value': '202006', 'label': 'Jun 2020'},
                            {'value': '202007', 'label': 'Jul 2020'},
                            {'value': '202008', 'label': 'Aug 2020'},
                            {'value': '202009', 'label': 'Sep 2020'},
                            {'value': '202010', 'label': 'Oct 2020'},
                            {'value': '202011', 'label': 'Nov 2020'},
                            {'value': '202012', 'label': 'Dec 2020'},
                            {'value': '202101', 'label': 'Jan 2021'},
                            {'value': '202102', 'label': 'Feb 2021'},
                            {'value': '202103', 'label': 'Mar 2021'},
                            {'value': '202104', 'label': 'Apr 2021'},
                            {'value': '202105', 'label': 'May 2021'},
                            {'value': '202106', 'label': 'Jun 2021'},
                            {'value': '202107', 'label': 'Jul 2021'},
                            {'value': '202108', 'label': 'Aug 2021'},
                            {'value': '202109', 'label': 'Sep 2021'}
                        ],
                        value='202001',
                        clearable=False
                    ),
                ],
            ),            
            
            html.Div(
                        [
                        "Travel time to care",
                        dcc.Dropdown(
                            id='model_var', 
                            options=[
                                {'value': 'Pop30mn', 
                                 'label': '30 min'},
                                {'value': 'Pop90mn', 
                                 'label': '90 min'},
                                {'value': 'Pop120mn', 
                                 'label': '120 min'},
                                {'value': 'Pop150mn', 
                                 'label': '150 min'},
                                {'value': 'Pop190mn', 
                                 'label': '190 min'}
                            ],
                            value='Pop30mn',
                            clearable=False
                    ),
                ],
            ),

            html.Div(
                [
                    "What to display:",
                    html.Button('i', className='info-button', 
                                id='layer-info-open-button'),
                    dcc.RadioItems(
                        id='display-element',
                        options=[
                            {'label': 'Access estimates by health zone', 'value': 'zone_data'},
                            {'label': 'High-res travel times', 'value': 'gha_raster'},
                            {'label': 'High-res population', 'value': 'world_pop'}
                        ],
                        value='zone_data'
                    )
                ],
            ),
            
            html.Div(
                [
                    "How to display accessibility:",
                    html.Button('i', className='info-button', 
                                id='display-info-open-button'),
                    dcc.RadioItems(
                        id='display-type',
                        options=[
                            {'value': 'choropleth', 'label': '% of pop. with access to services'},
                            {'value': 'per_capita', 'label': '% with access and size of pop.'},
                            {'value': 'absolute', 'label': 'Size of pop. without access'},
                        ],
                        value='per_capita'
                    )
                ],
            )
        ]),
        
        
        html.Div(id='density-container', children=[
            dcc.Graph(id='density',
                      config={'displayModeBar': False,
                              'scrollZoom': False}),
            html.Div(id='sources', 
                     children = ['Population data from ', 
                                 html.A('UN WorldPop', 
                                        href='https://population.un.org/wpp/'),
                                 html.Br(),
                                 'Travel time data from the ',
                                 html.A('GeoHealthAcess project',
                                        href='https://github.com/BLSQ/geohealthaccess/')
                                ]
                    )
                ]
            ),
        ]
    ),  
    html.Div(id = "map-container", 
                children=[
                    dcc.Loading(id='loading-icon',
                                children = [dcc.Graph(id="map-main",
                                                      hoverData={'points': 
                                                                 [{'text': 'Mikope'}]},
                                                      config={'displayModeBar': False})],
                                type="cube",
                                color="#157DC2")], 
                )

    
])

#########################################
#### callback and graphing functions ####
#########################################

@app.callback(
    Output("map-main", "figure"), 
    [Input("model_var", "value"),
     Input("month", "value"),
     Input("display-type", "value"),
     Input("display-element", "value")])
def display_map(model_var, month, display_type, display_element):

    time_to_care = ''.join([s for s in model_var if s.isdigit()])
    var_label_colorbar = f'% pop. within <br> {time_to_care} min of care <br>'
    
    if display_type == 'absolute':
        var_label_tooltip = f'Further than {time_to_care} min from care'
    else:
        var_label_tooltip = f'% pop. within {time_to_care} min of care'
    
    model_var = f'{model_var}_{month}'
    
    zone_opacity = 0.9
    
    custom_cb = dict(thicknessmode='fraction',
                     thickness=0.05,
                     ticks='inside',
                     xpad=28,
                     xanchor='right',
                     title=var_label_colorbar,
                     bgcolor='rgba(112, 128, 144, 0.72)',
                     tickfont_color='white',
                     tickcolor='white',
                     title_font_color='white',
                     ticksuffix='%',
                     outlinewidth=0)
    
    if display_element != 'zone_data':
        zone_opacity = 0

    # choropleth for proportions
    if (display_type == 'choropleth') & (display_element == 'zone_data'):
        fig = go.Figure(go.Choroplethmapbox(
                        geojson=json.loads(gdf.to_json()),
                        locations=gdf['fid'],
                        text=gdf['name'],
                        customdata=gdf[[model_var + '_Percent', 'Pop_readable']],
                        z=gdf[model_var + '_Percent'],
                        colorscale='rdbu',
                        colorbar=custom_cb,
                        marker=dict(opacity=zone_opacity),
                        hovertemplate = "<b>%{text}</b><br><br>" +
                                        "Population: <b>%{customdata[1]}</b><br>" +
                                        var_label_tooltip +": <b>~%{customdata[0]:.0f}%</b><br>" +
                                        "<extra></extra>",
                        showlegend=False,
                        meta='main'
        
        ))
        
    else:
        # Percent with access // population size markers
        if (display_type == 'per_capita') & (display_element == 'zone_data'):

            gdf['marker_size'] = gdf['PopTotal'] - gdf['PopTotal'].min()
            gdf['marker_size'] /= gdf['marker_size'].max()
            gdf['marker_size'] *= 1500
            
            fig = go.Figure(data=go.Scattermapbox(
                            lat=gdf['centroid_lat'],
                            lon=gdf['centroid_lon'],
                            text=gdf['name'],
                            customdata=gdf[[model_var + '_Percent', 'Pop_readable']],
                            marker=dict(
                                size=gdf['marker_size'],
                                sizemode='area',
                                color=gdf[model_var + '_Percent'],
                                colorscale='rdbu',
                                opacity=zone_opacity,
                                colorbar=custom_cb,
                            ),
                            hovertemplate = "<b>%{text}</b><br><br>" +
                                            "Population: <b>%{customdata[1]}</b><br>" +
                                            var_label_tooltip +": <b>~%{customdata[0]:.0f}%</b><br>" +
                                            "<extra></extra>",
                            showlegend=False,
                            meta='main'

            ))
        # Absolute population without access markers
        else:
            # rescale indicator for visualization
            gdf['absolute_w_out_access'] = gdf['PopTotal'] - gdf[model_var]
            gdf['marker_size'] = gdf['absolute_w_out_access'] - gdf['absolute_w_out_access'].min()
            gdf['marker_size'] /= gdf['PopTotal'].max()
            gdf['marker_size'] *= 1500
            
            gdf['absolute_w_out_access'] = gdf['absolute_w_out_access'].apply(lambda x: humanize_number(x))
            
            fig = go.Figure(data=go.Scattermapbox(
                lat=gdf['centroid_lat'],
                lon=gdf['centroid_lon'],
                text=gdf['name'],
                customdata=gdf[['absolute_w_out_access', 'Pop_readable']],
                marker=dict(
                    size=gdf['marker_size'],
                    sizemode='area',
                    color='#A5BAD2',
                    opacity=zone_opacity * 1.1,
                    colorbar=None,
                ),
                hovertemplate = "<b>%{text}</b><br><br>" +
                                "Population: <b>%{customdata[1]}</b><br>" +
                                var_label_tooltip +": <b>~%{customdata[0]}</b><br>" +
                                "<extra></extra>",
                showlegend=False,
                meta='main'

            ))
        
        marker_legend = pd.DataFrame(columns = ['display_name', 'lname', 'population', 
                                                'latitude', 'longitude'],
                                      data = [['', '2.5M population', 
                                               2500000, -11.48, 8.25],
                                              ['', '1M population', 
                                               1000000, -10.1, 8.25],
                                              ['', '500k population', 
                                               500000, -9.1, 8.25],
                                              ['', '250k population', 
                                               250000, -8.25, 8.25],
                                              ['Population scale <br><br><br>', '100k population', 
                                               100000, -7.6, 8.25]])
        
        marker_legend['marker_size'] = marker_legend['population'] / gdf['PopTotal'].max()
        marker_legend['marker_size'] *= 1500
        
        
        fig.add_trace(go.Scattermapbox(
            lat=marker_legend.latitude,
            lon=marker_legend.longitude,
            mode='markers+text',
            opacity=zone_opacity,
            marker=go.scattermapbox.Marker(
                size=marker_legend.marker_size,
                sizemode='area',
                color='#A5BAD2'
            ),
            showlegend=False,
            text=marker_legend.lname,
            textposition = 'middle right',
            textfont=dict(
                family="sans serif",
                size=12,
                color='#bfcdde'),
            hoverinfo="skip",
            hovertemplate=None,
        ))
    

    
    if display_element != 'zone_data':
        fig.update_traces(hoverinfo="skip",
                          hovertemplate=None,
                          marker_showscale=False)
        
    else:
        ## zone data hover formatting
        fig.update_layout(
            hoverlabel=dict(
                font_size=14
            )
        )
    
    if display_element == 'gha_raster':
        fig.update_layout(
            mapbox_layers=[
                {
                "sourcetype": "raster",
                "sourceattribution": "Bluesquare",
                "source": ["https://qgis-server.bluesquare.org"
                           "/cgi-bin/qgis_mapserv.fcgi?MAP=/home/qgis/projects"
                           "/geohealthaccess.qgz&service=WMS&request=GetMap"
                           f"&layers={month}_cost&styles=&format=image/png&transparent=true"
                           "&version=1.1.1&width=256&height=256"
                           "&srs=EPSG:3857&bbox={bbox-epsg-3857}"],
                "opacity" : 0.65

                }
            ]
        )
        
        colorbar_trace  = go.Scatter(x=[None],
                                     y=[None],
                                     mode='markers',
                                     marker=dict(
                                         colorscale='magma_r', 
                                         showscale=True,
                                         cmin=0,
                                         cmax=360,
                                         colorbar=dict(title=dict(text='Time to care <br> &nbsp;',
                                                                  font=dict(color='white')),
                                                       tickvals=[60, 120, 180, 
                                                                 240, 300, 360], 
                                                       ticktext=['1 hour', '2 hours',
                                                                 '3 hours', '4 hours',
                                                                 '5 hours', '6 hours'],
                                                       outlinewidth=0,
                                                       thicknessmode='fraction',
                                                       thickness=0.04,
                                                       ticks='inside',
                                                       xpad=28,
                                                       xanchor='right',
                                                       bgcolor='rgba(112, 128, 144, 0.72)',
                                                       tickfont_color='white',
                                                       tickcolor='white',
                                                       )
                                     ),
                                     hoverinfo='none'
                                    )
        
        fig['layout']['showlegend'] = False
        fig.add_trace(colorbar_trace)
        
    if display_element == 'world_pop':
        fig.update_layout(
            mapbox_layers=[
                {
                "sourcetype": "raster",
                "sourceattribution": "Bluesquare",
                "source": ["https://qgis-server.bluesquare.org"
                           "/cgi-bin/qgis_mapserv.fcgi?MAP=/home/qgis/projects"
                           "/test_wmts.qgz&service=WMS&request=GetMap"
                           "&layers=Population&styles=&format=image/png"
                           "&transparent=true&version=1.1.1&width=256&height=256"
                           "&srs=EPSG:3857&bbox={bbox-epsg-3857}"],
                "opacity" : 0.65   
                }
            ]
        )
        
        colorbar_trace  = go.Scatter(x=[None],
                             y=[None],
                             mode='markers',
                             marker=dict(
                                 colorscale='ylorbr', 
                                 showscale=True,
                                 cmin=0,
                                 cmax=53,
                                 colorbar=dict(title=dict(text='Population <br> &nbsp;',
                                                                  font=dict(color='white')),
                                               tickvals=[0, 10, 20, 30, 40, 50], 
                                               outlinewidth=0,
                                               thicknessmode='fraction',
                                               thickness=0.04,
                                               ticks='inside',
                                               xpad=28,
                                               xanchor='right',
                                               bgcolor='rgba(112, 128, 144, 0.72)',
                                               tickfont_color='white',
                                               tickcolor='white'                                               
                                               )
                             ),
                             hoverinfo='none'
                            )
 
        fig['layout']['showlegend'] = False
        fig.add_trace(colorbar_trace)
    
    
    fig.update_layout(mapbox=dict(style=style,
                                  accesstoken=token,
                                  center=go.layout.mapbox.Center(
                                      lat=-4.8514,
                                      lon=22.6780
                                  ),
                                  zoom=4.65
                                 )
                     )
    
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    fig.update_yaxes(visible=False, showticklabels=False)
    fig.update_xaxes(visible=False, showticklabels=False)
    
    return fig


@app.callback(
    Output("density", "figure"),
    Input("map-main", "hoverData"),
    Input("month", "value"),
    Input("display-element", "value"))
def cum_density_graph(hoverData, month, display_element):
    fig_color = '#7570b3'
    
    if display_element == 'zone_data':
        geo_unit_name = hoverData['points'][0]['text']
    
        tdf = gdf.drop(['geometry', 'PopTotal', 'Pop_readable', 
                        'centroid_lat', 'centroid_lon'], 
                   axis=1).loc[gdf.name == geo_unit_name]

        tdf = tdf.melt(id_vars=['fid', 'dhis2_code', 'name'])
        tdf = tdf.loc[tdf.variable.str.contains('Percent')]

        meta = tdf.variable.str.split('_', expand=True)

        tdf['var'] = meta[0]
        tdf['month'] = meta[1]

        name_dict = {'Pop30mn': 30,
                     'Pop90mn': 90,
                     'Pop120mn': 120,
                     'Pop150mn': 150,
                     'Pop190mn': 190}

        tdf['var'] = tdf['var'].replace(name_dict.keys(), name_dict.values())
        tdf = tdf.loc[tdf.month == month]
    else:
        geo_unit_name = ''
        tdf = pd.DataFrame(data=None, columns=['fid', 'dhis2_code', 'name', 
                                               'variable', 'value', 
                                               'var', 'month'])

    fig = go.Figure()
    
    fig.add_trace(go.Scatter(x=tdf['var'], 
                             y=tdf['value'],
                             fill='tozeroy',
                             name='',
                             mode='lines+markers',
                             hovertemplate='~%{y:.0f}% have access within %{x} min',
                             showlegend=False))
    
    fig.update_traces(marker_color=fig_color,
                      line_color=fig_color)

    fig.update_layout(margin={"r":0,"l":0,"b":0},
                      height=325,
                      yaxis_title='% with access',
                      xaxis_title='Travel time to care (min)',
                      title=geo_unit_name,
                      font=dict(size=10),
                      template='simple_white',
                      yaxis_range=[0,105],
                      xaxis_range=[20,200])

    return fig  

@app.callback(
    Output('display-type', 'options'),
    Input('display-element', 'value'))
def set_zone_data_radio_button_state(display_element):
    if 'zone_data' not in display_element:
        return [{'value': 'choropleth', 
                 'label': '% of pop. with access to services',
                 'disabled': True},
                {'value': 'per_capita', 
                 'label': '% with access and size of pop.',
                 'disabled': True},
                {'value': 'absolute', 
                 'label': 'Size of pop. without access',
                 'disabled': True}]
    else:
        return [{'value': 'choropleth', 
                 'label': '% of pop. with access to services',
                 'disabled': False},
                {'value': 'per_capita', 
                 'label': '% with access and size of pop.',
                 'disabled': False},
                {'value': 'absolute', 
                 'label': 'Size of pop. without access',
                 'disabled': False}]

@app.callback([Output('modal-content', 'children')],
              Output('modal', 'style'),
               [Input('modal-close-button', 'n_clicks'),
               Input('layer-info-open-button', 'n_clicks'),
               Input('display-info-open-button', 'n_clicks')])
def open_close_modal(close_n, open_layer_n, open_display_n):
    changed_id = [p['prop_id'] for p in dash.callback_context.triggered][0]
    
    if 'modal-close-button' in changed_id:
        if (close_n is not None) and (close_n > 0):
            return [html.Div([html.Button('Close', id='modal-close-button')]), 
                    {"display": "none"}]
    elif 'layer-info-open-button' in changed_id:
        if (open_layer_n is not None) and (open_layer_n > 0):
            return [html.Div([
                            html.H2('What to display'),
                            html.Div(children = [html.P(what_text[0]),
                                                 html.P(bold_before_colon(what_text[1])),
                                                 html.P(bold_before_colon(what_text[2])),
                                                 html.P(bold_before_colon(what_text[3])),
                                                 html.Ul(children = [
                                                     html.Li(what_text[4]),
                                                     html.Li(what_text[5]),
                                                     html.Li(what_text[6])
                                                 ]),
                                                 html.P(what_text[7])],
                                     id='modal-text'),
                            html.Button('Close', id='modal-close-button')]
                    ), 
                    {"display": "block"}]
    elif 'display-info-open-button' in changed_id:
        if (open_display_n is not None) and (open_display_n > 0):
            return [html.Div([
                            html.H2('How to display accessibility'),
                            html.Div(children = [html.P(how_text[0]),
                                                 html.Ul(children = [
                                                     html.Li(how_text[1]),
                                                     html.Li(how_text[2]),
                                                     html.Li(how_text[3])
                                                 ])],
                                     id='modal-text'),
                            html.Button('Close', id='modal-close-button')]
                    ), 
                    {"display": "block"}]
    else:
        return [html.Div([
                        html.H2(('Welcome to GeoHealthAccess for'
                                ' the Democratic Republic of Congo!'),
                                id='modal-title'),
                        html.Div([
                                html.P(landing_text[0]),
                                html.Ol([
                                    html.Li(children = [landing_text[1],
                                                        html.A(('high-resolution population'
                                                                ' maps made by WorldPop.'),
                                                          href='https://population.un.org/wpp/')]),
                                    html.Li(landing_text[2]),
                                    html.Li(landing_text[3]),
                                ]),
                                html.P(children = [landing_text[4],
                                                   html.A('Github.',
                                                          href=('https://github.com/BLSQ'
                                                                '/geohealthaccess/'))])
                        ], id = 'modal-text'),
                        html.Button('Close', id='modal-close-button')]
                    ), 
                    {"display": "block"}]

if __name__ == '__main__':
    if STANDALONE:
        app.run_server(port=8000, host='0.0.0.0', debug=False)
    else:
        app.run_server(port=8090, debug=True)
