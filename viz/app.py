# kaldjian
# 9 june 2021
# dash visualization of GHA modeling results

import os

STANDALONE = os.environ.get("STANDALONE", "yes") == "yes"

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

MAPBOX_TOKEN = os.environ.get(
    "MAPBOX_TOKEN",
    "pk.eyJ1IjoiYWthbGRqaWFuIiwiYSI6ImNrcnVvbzk2eDA2cnozMGxtM2ZwZ3B3bmUifQ.lUpko2ttQM904N8Zg1GB9w",
)
MAPBOX_STYLE = os.environ.get(
    "MAPBOX_STYLE", "mapbox://styles/akaldjian/ckrupp4jrbsbf17mstgsbtrti"
)

if STANDALONE:
    app = dash.Dash(__name__)
else:
    app = JupyterDash(__name__)

# app component layout
app.layout = html.Div(id="app-main", children=[
    
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
                                {'value': 'Pop60mn', 
                                 'label': '60 min'},
                                {'value': 'Pop90mn', 
                                 'label': '90 min'},
                                {'value': 'Pop120mn', 
                                 'label': '120 min'},
                                {'value': 'Pop180mn', 
                                 'label': '180 min'}
                            ],
                            value='Pop30mn',
                            clearable=False
                    ),
                ],
            ),

            html.Div(
                [
                    "Layers",
                    dcc.RadioItems(
                        id='display-elements',
                        options=[
                            {'label': 'Zone data', 'value': 'zone_data'},
                            {'label': 'Access raster', 'value': 'gha_raster'},
                            {'label': 'UN WorldPop', 'value': 'world_pop'}
                        ],
                        value='zone_data'
                    )
                ],
            ),
            
            html.Div(
                [
                    "Display",
                    dcc.RadioItems(
                        id='display-type',
                        options=[
                            {'value': 'markers', 'label': 'Markers'},
                            {'value': 'choropleth', 'label': 'Choropleth'},
                        ],
                        value='markers'
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
    
    dcc.Graph(id="map-main",
              hoverData={'points': [{'hovertext': 'ks Mikope Zone de Santé'}]},
              config={'displayModeBar': False}),   
])

# callback and graphing functions
@app.callback(
    Output("map-main", "figure"), 
    [Input("model_var", "value"),
     Input("month", "value"),
     Input("display-type", "value"),
     Input("display-elements", "value")])
def display_map(model_var, month, display_type, display_elements):
    
    time_to_care = ''.join([s for s in model_var if s.isdigit()])
    var_label_tooltip = f'% pop. within {time_to_care} min of care'
    var_label_colorbar = f'% pop. within <br> {time_to_care} min of care <br>'
    
    model_var = f'{model_var}_{month}'
    
    zone_opacity = 0.9
    
    if 'zone_data' not in display_elements:
        zone_opacity = 0

    # choropleth for proportions
    if (display_type == 'choropleth') & ('zone_data' in display_elements):
        fig = px.choropleth_mapbox(gdf,
                                   geojson=gdf.geometry, 
                                   locations='fid', 
                                   color=model_var + "_Percent",
                                   color_continuous_scale="rdbu",
                                   range_color=[0,100],
                                   opacity=zone_opacity,
                                   center={"lat": -4.8514, "lon":22.6780},
                                   zoom=4.65,
                                   hover_name='name',
                                   hover_data={'PopTotal':False,
                                               'fid':False,
                                               'Pop_readable':True},
                                   labels={model_var + '_Percent': var_label_tooltip,
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
                                center={"lat": -4.8514, "lon":22.6780},
                                zoom=4.65,
                                hover_name='name',
                                hover_data={'PopTotal':False,
                                            'fid':False,
                                            'centroid_lat': False,
                                            'centroid_lon': False,
                                            'Pop_readable':True},
                                labels={model_var + '_Percent': var_label_tooltip,
                                        'Pop_readable': 'Population'})
        
        marker_legend = pd.DataFrame(columns = ['display_name', 'lname', 'population', 
                                                'latitude', 'longitude'],
                                      data = [['', '2.5M population', 
                                               53, -11.48, 11.002433],
                                              ['', '1M population', 
                                               33, -10.1, 11.002433],
                                              ['', '500k population', 
                                               25, -9.1, 11.002433],
                                              ['', '250k population', 
                                               15, -8.4, 11.002433],
                                              ['Population scale <br><br><br>', '100k population', 
                                               10, -7.9, 11.002433]])
        
        fig.add_trace(go.Scattermapbox(
            lat=marker_legend.latitude,
            lon=marker_legend.longitude,
            mode='markers+text',
            opacity=zone_opacity,
            marker=go.scattermapbox.Marker(
                size=marker_legend.population,
                color='black'
            ),
            showlegend=False,
            text=marker_legend.display_name,
            textposition = 'bottom center',
            textfont=dict(
                family="sans serif",
                size=14),
            hoverinfo='text',
            hovertext=marker_legend.lname,
        ))
    
    
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
                                         colorscale='greens_r', 
                                         showscale=True,
                                         cmin=-5,
                                         cmax=5,
                                         colorbar=dict(title=dict(text='Time to care <br> &nbsp;',
                                                                  font=dict(color='white')),
                                                       tickvals=[-4.85, -1.626, 1.626, 4.85], 
                                                       ticktext=['<1 hour', '1-2 hours',
                                                                 '2-3 hours', '>3 hours'],
                                                       outlinewidth=0,
                                                       thicknessmode='fraction',
                                                       thickness=0.04,
                                                       ticks='inside',
                                                       xpad=8,
                                                       x=0.88,
                                                       bgcolor='rgba(112, 128, 144, 0.72)',
                                                       tickfont_color='white',
                                                       tickcolor='white',
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
                                               thickness=0.065,
                                               ticks='inside',
                                               xpad=8,
                                               x=0.9,
                                               bgcolor='rgba(112, 128, 144, 0.72)',
                                               tickfont_color='white',
                                               tickcolor='white'                                               
                                               )
                             ),
                             hoverinfo='none'
                            )
 
        fig['layout']['showlegend'] = False
        fig.add_trace(colorbar_trace)


    fig.update_layout(mapbox_style=MAPBOX_STYLE, mapbox_accesstoken=MAPBOX_TOKEN)

    fig.update_coloraxes(colorbar_thicknessmode='fraction',
                         colorbar_thickness=0.04,
                         colorbar_ticks='inside',
                         colorbar_xpad=8,
                         colorbar_x=0.9,
                         colorbar_title=var_label_colorbar,
                         colorbar_bgcolor='rgba(112, 128, 144, 0.72)',
                         colorbar_tickfont_color='white',
                         colorbar_tickcolor='white',
                         colorbar_title_font_color='white',
                         colorbar_ticksuffix='%')
    
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    fig.update_yaxes(visible=False, showticklabels=False)
    fig.update_xaxes(visible=False, showticklabels=False)
    
    return fig


@app.callback(
    Output("density", "figure"),
    Input("map-main", "hoverData"),
    Input("month", "value"),
    Input("display-elements", "value"))
def cum_density_graph(hoverData, month, display_elements):
    fig_color = '#7570b3'
    
    if 'zone_data' in display_elements:
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
    else:
        geo_unit_name = ''
        tdf = pd.DataFrame(data=None, columns=['fid', 'id', 'name', 
                                               'variable', 'value', 
                                               'var', 'month'])

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
                      height=325,
                      yaxis_title='% with access',
                      xaxis_title='Travel time to care (min)',
                      title=geo_unit_name,
                      font=dict(size=10))

    return fig  

@app.callback(
    Output('display-type', 'options'),
    Input('display-elements', 'value'))
def set_zone_data_radio_button_state(display_elements):
    if 'zone_data' not in display_elements:
        return [{'value': 'markers', 
                 'label': 'Markers',
                 'disabled': True},
                {'value': 'choropleth', 
                 'label': 'Choropleth',
                 'disabled': True}]
    else:
        return [{'value': 'markers', 
                 'label': 'Markers'},
                {'value': 'choropleth', 
                 'label': 'Choropleth'}]

if __name__ == '__main__':
    if STANDALONE:
        app.run_server(port=8000, host='0.0.0.0', debug=False)
    else:
        app.run_server(port=8090, debug=True)
