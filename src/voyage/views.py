from django.shortcuts import render
from django.db.models import Q,Prefetch
from django.http import HttpResponse, JsonResponse
from rest_framework.schemas.openapi import AutoSchema
from rest_framework import generics
from rest_framework.metadata import SimpleMetadata
from rest_framework.response import Response
from django.views.generic.list import ListView
import json
import requests
import time
from .models import Voyage
from .serializers import *

from .prefetch_settings import *

d=open('voyage/options.json','r')
voyage_options=(json.loads(d.read()))
d.close()

##flattener: https://stackoverflow.com/a/6027615
import collections
def flatten(d, parent_key='', sep='__'):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, collections.MutableMapping):
            items.extend(flatten(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

##RECURSIVE NEST-BUILDER
def addlevel(thisdict,keychain,payload):
	thiskey=keychain.pop(0)
	if len(keychain)>0:
		if thiskey not in thisdict:
			thisdict[thiskey]={}
		thisdict[thiskey]=addlevel(thisdict[thiskey],keychain,payload)
	else:
		thisdict[thiskey]=payload
	return thisdict

#GENERIC FUNCTION TO RUN A GET CALL ON VOYAGE-LIKE SERIALIZERS
def voyage_get(s,r,retrieve_all=False):
	queryset=Voyage.objects.all()
	#params=r.query_params // some of the request types are handled differently. had to use this at one point & don't want to forget
	params=r.GET

	#There are some real benefits to tuning this further. Right now I'm prefetching everything.
	#It pays off in terms of speed generally, but there is a bit of overhead with each prefetch.
	for p in prefetch_tables+prefetch_vars:
		#print(p)
		queryset=queryset.prefetch_related(p)

	#FIELD SELECTION
	## selected_fields
	### currently can only select tables one level down -- all the subsidiary fields come with it
	selected_fields=params.get('selected_fields')
	#print("====",selected_fields)

	if selected_fields!=None:
		selected_query_fields=[i for i in selected_fields.split(',')]
	else:
		selected_query_fields=None

	### NOW THE REAL VARIABLES
	#the base queryset contains all voyages
	#on stacking query vars: https://docs.djangoproject.com/en/3.2/topics/db/queries/#querysets-are-lazy

	####VOYAGE_ID COMMA-SEPARATED INTEGERS
	#now we just have to enumerate our varibles and build filters for them.
	voyage_ids=params.get('voyage_ids')
	if voyage_ids!=None:
		voyage_id=[int(i) for i in voyage_ids.split(',')]
		queryset = queryset.filter(voyage_id__in=voyage_id)

	#the below variables (numeric_fields, text_fields) were previously defined in fields.py (deleted)
	#now they are defined with a live call to the options endpoint
	#right now I'm assuming only two types of field: text and numeric
	#This live call slows things down, obviously, so it will be a good idea to have some caching in place
	#r=requests.options('http://127.0.0.1:8000/voyage/')
	#all_voyage_fields=json.loads(r.text)
	all_voyage_fields=voyage_options
	text_fields=[i for i in all_voyage_fields if 'CharField' in all_voyage_fields[i]['type']]
	numeric_fields=[i for i in all_voyage_fields if i not in text_fields]
	active_numeric_search_fields=[i for i in set(params).intersection(set(numeric_fields))]
		
	if len(active_numeric_search_fields)>0:

		for field in active_numeric_search_fields:
			min,max=[float(i) for i in params.get(field).split(',')]
			kwargs = {
			'{0}__{1}'.format(field, 'lte'): max,
			'{0}__{1}'.format(field, 'gte'): min
			}
		queryset=queryset.filter(**kwargs)
	
	active_text_search_fields=[i for i in set(params).intersection(set(text_fields))]
	if len(active_text_search_fields)>0:
		for field in active_text_search_fields:
			searchstring=params.get(field)
			kwargs = {
			'{0}__{1}'.format(field, 'icontains'): searchstring
			}
		queryset=queryset.filter(**kwargs)


	#PAGINATION/LIMITS
	## results_per_page
	## results_page
	if retrieve_all==False:
		default_results_per_page=10
		default_results_page=0
		results_per_page=params.get('results_per_page')

		if results_per_page==None:
			results_per_page=default_results_per_page
		else:
			results_per_page=int(results_per_page)

		results_page=params.get('results_page')
		if results_page==None:
			results_page=default_results_page
		else:
			results_page=int(results_page)

		start_idx=results_page*results_per_page
		end_idx=(results_page+1)*results_per_page
		queryset=queryset[start_idx:end_idx]

	return queryset,selected_query_fields


#LONG-FORM TABULAR ENDPOINT. PAGINATION IS A NECESSITY HERE!
##HAVE NOT YET BUILT IN ORDER-BY FUNCTIONALITY
class VoyageList(generics.GenericAPIView):
	serializer_class=VoyageSerializer
	def options(self,request):
		return JsonResponse(voyage_options,safe=False)
	def get(self,request):
		queryset,selected_query_fields=voyage_get(self,request)
		read_serializer=VoyageSerializer(queryset,many=True,selected_fields=selected_query_fields)
		return JsonResponse(read_serializer.data,safe=False)

#VOYAGES SCATTER DATAFRAME ENDPOINT (experimental and going to be a resource hog!)
class VoyageDataFrames(generics.GenericAPIView):
	def get(self,request):
		times=[]
		print("FETCHING...")
		times.append(time.time())
		queryset,selected_query_fields=voyage_get(self,request,retrieve_all=True)
		times.append(time.time())
		serialized=VoyageSerializer(queryset,many=True,selected_fields=selected_query_fields).data
		times.append(time.time())
		output_dicts=[]
		for i in serialized:
			flat_dictionary=flatten(i)
			output_dicts.append(flat_dictionary)
		times.append(time.time())
		dict_keys=[i for i in output_dicts[0].keys()]
		final={k:[] for k in selected_query_fields}
		times.append(time.time())
		for d in output_dicts:
			for k in final:
				#need a null value handler here -- this one is not great, I will grant
				#but the serializer, on a nested field, will return an upstream null, which is hard to parse, e.g.:
				##http://0.0.0.0:8000/voyage/dataframes?voyage_itinerary__imp_principal_region_slave_dis__region=Virginia&selected_fields=voyage_itinerary__imp_broad_region_voyage_begin__broad_region
				##will get you a value like: {'voyage_itinerary__imp_broad_region_voyage_begin__broad_region': 'Europe'}
				##but legit nulls come back like this too: {'voyage_itinerary__imp_broad_region_voyage_begin': None}
				try:
					final[k].append(d[k])
				except:
					final[k].append(None)
		for i in range(1,len(times)):
			print(times[i]-times[i-1])
		return JsonResponse(final,safe=False)
