#!/usr/bin/env python
# coding=UTF-8

import sys
import csv
import os
import os.path
import urllib.parse
from uuid import uuid4
from datetime import datetime, timedelta
from rdflib import ConjunctiveGraph, Namespace, URIRef, BNode, Literal
from rdflib.plugin import register, Serializer
from rdflib.namespace import RDF, RDFS, FOAF, XSD

if len(sys.argv) != 3:
    print('Usage: csv2np.py path_to_csv output_dir')
    sys.exit(1)

csvpath = sys.argv[1]
out_dir = sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
csv_headers = []

DDC = Namespace('http://digitalduchemin.org/')
NP = Namespace('http://www.nanopub.org/nschema#')
PROV = Namespace('http://www.w3.org/ns/prov#')
OA = Namespace("http://www.w3.org/ns/oa#")
DCTYPES = Namespace("http://purl.org/dc/dcmitype/")
CNT = Namespace("http://www.w3.org/2011/content#")

CONTEXT = {
    "ddc": DDC,
    "np": NP,
    "prov": PROV,
    "oa": OA,
    "dctypes": DCTYPES,
    "foaf": FOAF,
    "cnt": CNT
}


class Nanopub(object):
    def __init__(self, data, given_id=None):
        """ Create a nanopublication graph """
        g = self.g = ConjunctiveGraph()
        self.data = data

        if not given_id:
            given_id = str(uuid4())

        np = DDC.term("np" + given_id)
        np_ns = Namespace(np + "#")

        assertion = self.assertion = URIRef(np_ns.assertion)
        provenance = self.provenance = URIRef(np_ns.provenance)
        pubinfo = self.pubInfo = URIRef(np_ns.pubinfo)

        # Pubinfo
        ema = "Enhanching Music Notation Addressability Project"
        g.add((np, PROV.wasAttributedTo, Literal(ema), pubinfo))

        # Provenance
        date = data[25]
        try:
            creation_date = datetime.strptime(date, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            creation_date = datetime.strptime(date, "%b %d, %Y %I:%M %p")
            creation_date = creation_date + timedelta(seconds=0)

        creation_date = creation_date.strftime('%Y-%m-%dT%H:%M:%S-05:00')
        timestamp = Literal(creation_date, datatype=XSD.dateTime)
        g.add((assertion, PROV.generatedAtTime, timestamp, provenance))

        analyst = Literal(data[28])
        g.add((assertion, PROV.wasAttributedTo, analyst, provenance))

        # Assertion (OA)
        observation = BNode()
        g.add((observation, RDF.type, OA.Annotation, assertion))
        g.add((observation, OA.annotatedBy, analyst, assertion))

        # OA tags for analytical statements
        columns = [1, 2, 3, 5, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19, 2,
                   21, 22, 23, 24, 26, 27, 29, 30, 31, 32, 33, 34, 35, 36, 37]
        forbidden_values = ["none", "nocadence", ""]

        for l in columns:
            value = data[l].strip()
            if value.lower() not in forbidden_values:
                label = csv_headers[l].strip()
                self.addAssertionTag(label, value, observation)

        # OA body for free text comment
        comment = data[0].strip()
        if comment.lower() not in forbidden_values:
            body = BNode()

            g.add((observation, OA.motivatedBy, OA.commenting, assertion))

            g.add((body, RDF.type, DCTYPES.Text, assertion))
            g.add((body, RDF.type, CNT.ContentAsText, assertion))
            g.add((body, CNT.chars, Literal(comment), assertion))

            g.add((observation, OA.hasBody, body, assertion))

        # OA target
        target = URIRef(self.buildEMAurl())
        g.add((observation, OA.hasTarget, target))

        # NP main graph

        g.add((np, RDF.type, NP.Nanopublication))
        g.add((np, NP.hasAssertion, assertion))
        g.add((np, NP.hasProvenance, provenance))
        g.add((np, NP.hasPublicationInfo, pubinfo))

    def addAssertionTag(self, label, value, observation):
        tag = BNode()

        self.g.add((observation, OA.motivatedBy, OA.tagging, self.assertion))
        self.g.add((observation, OA.motivatedBy, OA.identifying,
                    self.assertion))

        self.g.add((tag, RDF.type, OA.Tag, self.assertion))
        self.g.add((tag, RDFS.label, Literal(label), self.assertion))
        self.g.add((tag, RDF.value, Literal(value), self.assertion))
        self.g.add((observation, OA.motivatedBy, OA.identifying,
                    self.assertion))

        self.g.add((observation, OA.hasBody, tag, self.assertion))

    def buildEMAurl(self):
        d = self.data
        measures = "{0}-{1}".format(d[8], d[18])
        staves = []

        staff_data = [10, 20, 26, 31, 32, 21, 9, 2, 16, 7, 17, 14, 24, 37, 23,
                      35, 34, 29, 5, 12, 22]

        for s in staff_data:
            r_id = self.roleToIndex(d[s])
            if r_id and r_id not in staves:
                staves.append(r_id)

        # remove duplicate values
        staves = list(set(staves))
        staves_str = ",".join(str(x) for x in staves)

        if not staves_str:
            staves_str = "all"

        dc_id = d[6][:6].upper()
        dcfile = "http://digitalduchemin.org/mei/{0}.xml".format(dc_id)
        dcfile = urllib.parse.quote(dcfile, "")

        return "http://ema.mith.org/{0}/{1}/{2}/@all".format(dcfile,
                                                             measures,
                                                             staves_str)

    def roleToIndex(self, r):
        r = r.lower()
        roles = [None, "s", "ct", "t", "b"]
        if r in roles:
            return roles.index(r)
        else:
            return None

    def jsonld(self, indent=2):
        return self.g.serialize(format='json-ld',
                                indent=indent, context=CONTEXT)

    def trig(self, indent=2):
        return self.g.serialize(format='trig')

with open(csvpath) as csvfile:
    creader = csv.reader(csvfile)
    for i, analysis in enumerate(creader):
        if i == 0:
            csv_headers = analysis
        else:
            n = Nanopub(analysis, str(i))
            filename = "np{0}.jsonld".format(i)
            with open(os.path.join(out_dir, filename), 'wb') as f:
                j = n.jsonld()
                f.write(j)

register('json-ld', Serializer, 'rdflib_jsonld.serializer', 'JsonLDSerializer')