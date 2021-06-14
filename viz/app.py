# kaldjian
# 9 june 2021
# dash visualization of GHA modeling results

##############################################
##### jupyter dash setup + package imports ###
##############################################

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


######################
#### data imports ####
######################

gdf = gpd.read_file('s3://habari-test-lake/gha-viz/data/DRC_Stats_Service.geojson')

gdf['fid'] = gdf['fid'] - 1
gdf['Pop_readable'] = gdf['PopTotal'].apply(lambda x: humanize_number(x))

gdf['centroid_lat'] = gdf['geometry'].centroid.y
gdf['centroid_lon'] = gdf['geometry'].centroid.x


########################
#### dash app setup ####
########################

app = JupyterDash(__name__)

# app component layout
app.layout = html.Div(id="app-main", children=[
    
    dcc.Graph(id="map-main",
              hoverData={'points': [{'hovertext': 'ks Mikope Zone de Santé'}]}),
    
    html.Div(id='sidebar', children=[
        
        html.Div(id='ctrls-container', children=[
            html.Div(
                        [
                        "GHA Variable",
                        dcc.Dropdown(
                            id='model_var', 
                            options=[
                                {'value': 'Pop30mn', 
                                 'label': 'Pop within 30 min of care'},
                                {'value': 'Pop60mn', 
                                 'label': 'Pop within 60 min of care'},
                                {'value': 'Pop90mn', 
                                 'label': 'Pop within 90 min of care'},
                                {'value': 'Pop120mn', 
                                 'label': 'Pop within 120 min of care'},
                                {'value': 'Pop180mn', 'label': 
                                 'Pop within 180 min of care'}
                            ],
                            value='Pop30mn',
                            clearable=False
                    ),
                ],
            ),


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
                        ],
                        value='202001',
                        clearable=False
                    ),
                ],
            ),


            html.Div(
                [
                    "Display",
                    dcc.RadioItems(
                        id='metric',
                        options=[
                            {'value': '', 'label': 'Markers'},
                            {'value': '_Percent', 'label': 'Choropleth'},
                        ],
                        value=''
                    )
                ],
            ),

            html.Div(
                [
                    "Layers",
                    dcc.RadioItems(
                        id='display_elements',
                        options=[
                            {'label': 'Zone data', 'value': 'zone_data'},
                            {'label': 'Access raster', 'value': 'gha_raster'},
                            {'label': 'UN WorldPop', 'value': 'world_pop'}
                        ],
                        value='zone_data'
                    )
                ],
            )]
        ),
        
        
        html.Div(id='density-container', children=[
             dcc.Graph(id='density',
                  config={'displayModeBar': False,
                          'scrollZoom': False})
                ]
            ),
        ]
    ),     
])

# callback and graphing functions
@app.callback(
    Output("map-main", "figure"), 
    [Input("model_var", "value"),
     Input("month", "value"),
     Input("metric", "value"),
     Input("display_elements", "value")])
def display_map(model_var, month, metric, display_elements):
    
    var_label = "% of population" # f'% pop. within {model_var[3:5]} min of care'
    
    model_var = f'{model_var}_{month}{metric}'
    
    zone_opacity = 0.9
    
    if 'zone_data' not in display_elements:
        zone_opacity = 0

    # choropleth for proportions
    if metric == '_Percent':
        fig = px.choropleth_mapbox(gdf,
                                   geojson=gdf.geometry, 
                                   locations='fid', 
                                   color=model_var,
                                   color_continuous_scale="rdbu",
                                   range_color=[0,100],
                                   opacity=zone_opacity,
                                   center={"lat": -3.8114, "lon":21.6780},
                                   mapbox_style="carto-positron",
                                   zoom=4.5,
                                   hover_name='name',
                                   hover_data={'PopTotal':False,
                                               'fid':False,
                                               'Pop_readable':True},
                                   labels={model_var: var_label,
                                           'Pop_readable': 'Population'})
        
    else:
        fig = px.scatter_mapbox(gdf,
                                lat='centroid_lat',
                                lon='centroid_lon',
                                color=model_var + '_Percent',
                                color_continuous_scale="rdbu",
                                range_color=[0,100],
                                size='PopTotal',
                                size_max=40,
                                opacity=zone_opacity,
                                center={"lat": -3.8114, "lon":21.6780},
                                mapbox_style="carto-positron",
                                zoom=4.5,
                                hover_name='name',
                                hover_data={'PopTotal':False,
                                            'fid':False,
                                            'centroid_lat': False,
                                            'centroid_lon': False,
                                            'Pop_readable':True},
                                labels={model_var + '_Percent': var_label,
                                        'Pop_readable': 'Population'})
        
#         TODO: add size legend in marker form
#         fig.add_trace(go.Scattermapbox(
#             lat=['-5.956295'],
#             lon=['11.04126'],
#             mode='markers',
#             marker=go.scattermapbox.Marker(
#                 size=25
#             ),
#             text=['Test'],
#             showlegend=False
#         ))
    
    
    if 'zone_data' not in display_elements:
        fig.update_traces(hoverinfo="skip", 
                          hovertemplate=None,
                          marker_coloraxis=None)
    
    if 'gha_raster' in display_elements:
        fig.update_layout(
            mapbox_layers=[
                {
                "sourcetype": "raster",
                "sourceattribution": "Bluesquare",
                "source": ["https://qgis-server.bluesquare.org"
                           "/cgi-bin/qgis_mapserv.fcgi?MAP=/home/qgis/projects"
                           "/GHA_ISO_COST.qgz&service=WMS&request=GetMap&layers"
                           "=cost_car_iso_f5f38704_ba1e_4a6d_a5ee_fd1752fa9cf3&styles="
                           "&format=image/png&transparent=true&version=1.1.1&width=256&height=256"
                           "&srs=EPSG:3857&bbox={bbox-epsg-3857}"],
                "opacity" : 0.65

                }
            ]
        )
        
        colorbar_trace  = go.Scatter(x=[None],
                                     y=[None],
                                     mode='markers',
                                     marker=dict(
                                         colorscale='greens', 
                                         showscale=True,
                                         cmin=-5,
                                         cmax=5,
                                         colorbar=dict(tickvals=[-4.8, 4.8], 
                                                       ticktext=['Low', 'High'], 
                                                       outlinewidth=0,
                                                       x=-0.1,
                                                       xpad=15
                                                       )
                                     ),
                                     hoverinfo='none'
                                    )
        
        fig['layout']['showlegend'] = False
        fig.add_trace(colorbar_trace)
        
    if 'world_pop' in display_elements:
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
                "opacity" : 0.4   
                }
            ]
        )
        
        colorbar_trace  = go.Scatter(x=[None],
                             y=[None],
                             mode='markers',
                             marker=dict(
                                 colorscale='ylorbr', 
                                 showscale=True,
                                 cmin=-5,
                                 cmax=5,
                                 colorbar=dict(tickvals=[-4.8, 4.8], 
                                               ticktext=['Low', 'High'], 
                                               outlinewidth=0,
                                               x=-0.1,
                                               xpad=15
                                               )
                             ),
                             hoverinfo='none'
                            )
 
        fig['layout']['showlegend'] = False
        fig.add_trace(colorbar_trace)
        
        
    fig.update_coloraxes(colorbar_x=-0.1,
                         colorbar_xpad=15)
    
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    fig.update_yaxes(visible=False, showticklabels=False)
    fig.update_xaxes(visible=False, showticklabels=False)
    
    return fig



@app.callback(
    Output("density", "figure"),
    Input("map-main", "hoverData"),
    Input("month", "value"))
def cum_density_graph(hoverData, month):
    fig_color = '#7570b3'
    
    geo_unit_name = hoverData['points'][0]['hovertext']
    
    tdf = gdf.drop(['geometry', 'PopTotal', 'Pop_readable', 
                    'centroid_lat', 'centroid_lon'], 
               axis=1).loc[gdf.name == geo_unit_name]

    tdf = tdf.melt(id_vars=['fid', 'id', 'name'])
    tdf = tdf.loc[tdf.variable.str.contains('Percent')]

    meta = tdf.variable.str.split('_', expand=True)

    tdf['var'] = meta[0]
    tdf['month'] = meta[1]

    name_dict = {'Pop30mn': 30,
                 'Pop60mn': 60,
                 'Pop90mn': 90,
                 'Pop120mn': 120,
                 'Pop180mn': 180}

    tdf['var'] = tdf['var'].replace(name_dict.keys(), name_dict.values())
    tdf = tdf.loc[tdf.month == month]

    fig = px.area(tdf, 
                 x="var", y="value",
                 range_y=[0,105],
                 template='simple_white')
    
    fig.add_trace(go.Scatter(x=tdf['var'], 
                             y=tdf['value'],
                             name='',
                             mode='markers',
                             hovertemplate='%{y}% have access within %{x} min',
                             showlegend=False))
    
    fig.update_traces(marker_color=fig_color,
                      line_color=fig_color)

    fig.update_layout(margin={"r":0,"l":0,"b":0},
                      yaxis_title='% with access',
                      xaxis_title='Travel time to care (min)',
                      title=geo_unit_name,
                      font=dict(size=10))

    return fig  

if __name__ == '__main__':
    app.run_server(port=8090, debug=True)
    