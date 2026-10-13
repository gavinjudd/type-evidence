#!/usr/bin/env python3
"""Build offline directory metadata from saved official Google snapshots.

No networking, font downloads, or third-party parser is used. The commercial
selection below records names and retail links checked against official foundry
catalogs; it contains no copied descriptions, specimens, or font binaries.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import quote, urlparse

# Selected retail listings reviewed 2026-10-13. Counts are provider listings;
# a listing can be a family, a subfamily, or a collection. Unknowns stay unknown.
COMMERCIAL_SOURCES = [
  {
    "id": "klim",
    "provider": "Klim Type Foundry",
    "url": "https://klim.co.nz/fonts/",
    "retrieved_at": "2026-10-13T01:35:55Z",
    "sha256": "1707d2f9a10b7da64c8af3c3a0cc4464cc743a509409d61b6f842f6fd2000afd",
    "kind": "official-foundry-catalog",
    "license_url": "https://klim.co.nz/licences/"
  },
  {
    "id": "grilli-type",
    "provider": "Grilli Type",
    "url": "https://www.grillitype.com/typefaces",
    "retrieved_at": "2026-10-13T01:35:55Z",
    "sha256": "511aa24946c9fa24759d7e01fdece143ba5ba6b9d1eb8ad795e59a9428b4fa9c",
    "kind": "official-foundry-catalog",
    "license_url": "https://www.grillitype.com/information"
  },
  {
    "id": "pangram-pangram",
    "provider": "Pangram Pangram",
    "url": "https://pangrampangram.com/collections/fonts",
    "retrieved_at": "2026-10-13T01:35:55Z",
    "sha256": "00fdbd53b9c80aa11579c09c84c81f37a37b88bfc94d74a6ab410828520724c7",
    "kind": "official-foundry-catalog",
    "license_url": "https://pangrampangram.com/pages/eula"
  },
  {
    "id": "displaay",
    "provider": "Displaay",
    "url": "https://displaay.net/typefaces/",
    "retrieved_at": "2026-10-13T01:35:55Z",
    "sha256": "11fd15c933dcc5e28700b4847a82e814c4e72e970f97eefcdc7512381e26dac3",
    "kind": "official-foundry-catalog",
    "license_url": "https://displaay.net/help/licenses"
  },
  {
    "id": "swiss-typefaces",
    "provider": "Swiss Typefaces",
    "url": "https://www.swisstypefaces.com/fonts/",
    "retrieved_at": "2026-10-13T01:35:55Z",
    "sha256": "c47dedc0638a32272456a70fe76fa8f2d6f9bbc0be9daf3265c177622d0ae01c",
    "kind": "official-foundry-catalog",
    "license_url": "https://www.swisstypefaces.com/licensing/"
  },
  {
    "id": "commercial-type",
    "provider": "Commercial Type",
    "url": "https://commercialtype.com/catalog",
    "retrieved_at": "2026-10-13T01:35:55Z",
    "sha256": "f4ba02ffdac31106afe4aff16b0a0d1e70f1e3d14c24d669c4eb6a1ca76e7cb6",
    "kind": "official-foundry-catalog",
    "license_url": "https://commercialtype.com/eula"
  },
  {
    "id": "dinamo",
    "provider": "Dinamo",
    "url": "https://abcdinamo.com/catalogue",
    "retrieved_at": "2026-10-13T01:35:55Z",
    "sha256": "ece7cd7ed74d7f66e7aa3c9b0eb1587a618b078ddd65530fedb3663c72ed6336",
    "kind": "official-foundry-catalog",
    "license_url": None
  }
]

COMMERCIAL_FAMILIES = [
    {'provider_key': 'commercial-type', 'family': 'Algebra', 'source_url': 'https://commercialtype.com/catalog/algebra', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Atlas', 'source_url': 'https://commercialtype.com/catalog/atlas', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Austin', 'source_url': 'https://commercialtype.com/catalog/austin', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Canela', 'source_url': 'https://commercialtype.com/catalog/canela', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Caponi', 'source_url': 'https://commercialtype.com/catalog/caponi', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Chiswick Sans', 'source_url': 'https://commercialtype.com/catalog/chiswick_sans', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Chiswick Serif', 'source_url': 'https://commercialtype.com/catalog/chiswick_serif', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Dala Floda', 'source_url': 'https://commercialtype.com/catalog/dala_floda', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Darby Sans', 'source_url': 'https://commercialtype.com/catalog/darby_sans', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Darby Serif', 'source_url': 'https://commercialtype.com/catalog/darby_serif', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Druk', 'source_url': 'https://commercialtype.com/catalog/druk', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Feature', 'source_url': 'https://commercialtype.com/catalog/feature', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Focal', 'source_url': 'https://commercialtype.com/catalog/focal', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Graphik', 'source_url': 'https://commercialtype.com/catalog/graphik', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Guardian Egyptian', 'source_url': 'https://commercialtype.com/catalog/guardian_egyptian', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Lyon', 'source_url': 'https://commercialtype.com/catalog/lyon', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Marr Sans', 'source_url': 'https://commercialtype.com/catalog/marr_sans', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Neue Haas Grotesk', 'source_url': 'https://commercialtype.com/catalog/neue_haas_grotesk', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Platform', 'source_url': 'https://commercialtype.com/catalog/platform', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Portrait', 'source_url': 'https://commercialtype.com/catalog/portrait', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Produkt', 'source_url': 'https://commercialtype.com/catalog/produkt', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Publico', 'source_url': 'https://commercialtype.com/catalog/publico', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Stag', 'source_url': 'https://commercialtype.com/catalog/stag', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'commercial-type', 'family': 'Styrene', 'source_url': 'https://commercialtype.com/catalog/styrene', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'dinamo', 'family': 'Areal', 'source_url': 'https://abcdinamo.com/typefaces/areal', 'category': 'unknown', 'variable': True, 'style_count': 36, 'tags': ['mono', 'sans', 'semi-mono']},
    {'provider_key': 'dinamo', 'family': 'Arizona', 'source_url': 'https://abcdinamo.com/typefaces/arizona', 'category': 'unknown', 'variable': True, 'style_count': 150, 'tags': ['sans', 'serif']},
    {'provider_key': 'dinamo', 'family': 'Asfalt', 'source_url': 'https://abcdinamo.com/typefaces/asfalt', 'category': 'unknown', 'variable': True, 'style_count': 20, 'tags': ['display', 'sans']},
    {'provider_key': 'dinamo', 'family': 'BINGO', 'source_url': 'https://abcdinamo.com/typefaces/bingo', 'category': 'unknown', 'variable': None, 'style_count': 2, 'tags': ['display', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Camera', 'source_url': 'https://abcdinamo.com/typefaces/camera', 'category': 'unknown', 'variable': True, 'style_count': 40, 'tags': ['display', 'mono', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Camera Rounded', 'source_url': 'https://abcdinamo.com/typefaces/camera-rounded', 'category': 'unknown', 'variable': True, 'style_count': 40, 'tags': ['display', 'mono', 'rounded', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Connect', 'source_url': 'https://abcdinamo.com/typefaces/connect', 'category': 'unknown', 'variable': None, 'style_count': 20, 'tags': ['display', 'mono']},
    {'provider_key': 'dinamo', 'family': 'Diatype', 'source_url': 'https://abcdinamo.com/typefaces/diatype', 'category': 'unknown', 'variable': True, 'style_count': 112, 'tags': ['mono', 'sans', 'semi-mono']},
    {'provider_key': 'dinamo', 'family': 'Diatype Extra', 'source_url': 'https://abcdinamo.com/typefaces/diatype-extra', 'category': 'unknown', 'variable': None, 'style_count': 40, 'tags': ['mono', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Diatype Rounded', 'source_url': 'https://abcdinamo.com/typefaces/diatype-rounded', 'category': 'unknown', 'variable': True, 'style_count': 48, 'tags': ['mono', 'rounded', 'sans', 'semi-mono']},
    {'provider_key': 'dinamo', 'family': 'Favorit', 'source_url': 'https://abcdinamo.com/typefaces/favorit', 'category': 'unknown', 'variable': True, 'style_count': 112, 'tags': ['mono', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Gaisyr', 'source_url': 'https://abcdinamo.com/typefaces/gaisyr', 'category': 'unknown', 'variable': True, 'style_count': 42, 'tags': ['mono', 'semi-mono', 'serif']},
    {'provider_key': 'dinamo', 'family': 'Galapagos', 'source_url': 'https://abcdinamo.com/typefaces/galapagos', 'category': 'display', 'variable': None, 'style_count': 70, 'tags': ['display']},
    {'provider_key': 'dinamo', 'family': 'Ginto', 'source_url': 'https://abcdinamo.com/typefaces/ginto', 'category': 'sans-serif', 'variable': True, 'style_count': 64, 'tags': ['sans']},
    {'provider_key': 'dinamo', 'family': 'Ginto Rounded', 'source_url': 'https://abcdinamo.com/typefaces/ginto-rounded', 'category': 'sans-serif', 'variable': True, 'style_count': 48, 'tags': ['rounded', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Gramercy', 'source_url': 'https://abcdinamo.com/typefaces/gramercy', 'category': 'unknown', 'variable': True, 'style_count': 48, 'tags': ['display', 'serif']},
    {'provider_key': 'dinamo', 'family': 'Gravity', 'source_url': 'https://abcdinamo.com/typefaces/gravity', 'category': 'unknown', 'variable': True, 'style_count': 96, 'tags': ['display', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Grow', 'source_url': 'https://abcdinamo.com/typefaces/grow', 'category': 'unknown', 'variable': None, 'style_count': 63, 'tags': ['display', 'normal', 'sans', 'static', 'weight', 'width', 'xtremeweight']},
    {'provider_key': 'dinamo', 'family': 'Helveesti', 'source_url': 'https://abcdinamo.com/typefaces/helveesti', 'category': 'unknown', 'variable': True, 'style_count': 64, 'tags': ['display', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Honeymoon', 'source_url': 'https://abcdinamo.com/typefaces/honeymoon', 'category': 'unknown', 'variable': True, 'style_count': 8, 'tags': ['display', 'mono']},
    {'provider_key': 'dinamo', 'family': 'Laica', 'source_url': 'https://abcdinamo.com/typefaces/laica', 'category': 'unknown', 'variable': True, 'style_count': 20, 'tags': ['mono', 'serif']},
    {'provider_key': 'dinamo', 'family': 'Marfa', 'source_url': 'https://abcdinamo.com/typefaces/marfa', 'category': 'unknown', 'variable': True, 'style_count': 42, 'tags': ['mono', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Marist', 'source_url': 'https://abcdinamo.com/typefaces/marist', 'category': 'serif', 'variable': True, 'style_count': 12, 'tags': ['serif']},
    {'provider_key': 'dinamo', 'family': 'Maxi', 'source_url': 'https://abcdinamo.com/typefaces/maxi', 'category': 'unknown', 'variable': True, 'style_count': 12, 'tags': ['display', 'mono', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Monument Grotesk', 'source_url': 'https://abcdinamo.com/typefaces/monument-grotesk', 'category': 'unknown', 'variable': True, 'style_count': 64, 'tags': ['mono', 'sans', 'semi-mono']},
    {'provider_key': 'dinamo', 'family': 'Oracle', 'source_url': 'https://abcdinamo.com/typefaces/oracle', 'category': 'unknown', 'variable': True, 'style_count': 36, 'tags': ['mono', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Oracle Rounded', 'source_url': 'https://abcdinamo.com/typefaces/oracle-rounded', 'category': 'unknown', 'variable': True, 'style_count': 36, 'tags': ['mono', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Otto', 'source_url': 'https://abcdinamo.com/typefaces/otto', 'category': 'serif', 'variable': True, 'style_count': 8, 'tags': ['serif']},
    {'provider_key': 'dinamo', 'family': 'Pareto', 'source_url': 'https://abcdinamo.com/typefaces/pareto', 'category': 'unknown', 'variable': None, 'style_count': 3, 'tags': ['display', 'serif']},
    {'provider_key': 'dinamo', 'family': 'Pelikan', 'source_url': 'https://abcdinamo.com/typefaces/pelikan', 'category': 'unknown', 'variable': True, 'style_count': 80, 'tags': ['mono', 'sans', 'semi-mono']},
    {'provider_key': 'dinamo', 'family': 'Prophet', 'source_url': 'https://abcdinamo.com/typefaces/prophet', 'category': 'sans-serif', 'variable': True, 'style_count': 12, 'tags': ['sans']},
    {'provider_key': 'dinamo', 'family': 'Publisher', 'source_url': 'https://abcdinamo.com/typefaces/publisher', 'category': 'unknown', 'variable': True, 'style_count': 72, 'tags': ['sans', 'slab']},
    {'provider_key': 'dinamo', 'family': 'Repro', 'source_url': 'https://abcdinamo.com/typefaces/repro', 'category': 'unknown', 'variable': True, 'style_count': 45, 'tags': ['mono', 'sans']},
    {'provider_key': 'dinamo', 'family': 'ROM', 'source_url': 'https://abcdinamo.com/typefaces/rom', 'category': 'unknown', 'variable': True, 'style_count': 84, 'tags': ['mono', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Schengen', 'source_url': 'https://abcdinamo.com/typefaces/schengen', 'category': 'unknown', 'variable': True, 'style_count': 162, 'tags': ['display', 'mono', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Social', 'source_url': 'https://abcdinamo.com/typefaces/social', 'category': 'unknown', 'variable': True, 'style_count': 64, 'tags': ['mono', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Solar', 'source_url': 'https://abcdinamo.com/typefaces/solar', 'category': 'unknown', 'variable': True, 'style_count': 64, 'tags': ['display', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Stefan', 'source_url': 'https://abcdinamo.com/typefaces/stefan-marx', 'category': 'unknown', 'variable': None, 'style_count': 3, 'tags': ['display', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Synt', 'source_url': 'https://abcdinamo.com/typefaces/synt', 'category': 'unknown', 'variable': True, 'style_count': 25, 'tags': ['mono', 'serif']},
    {'provider_key': 'dinamo', 'family': 'Walter', 'source_url': 'https://abcdinamo.com/typefaces/walter', 'category': 'unknown', 'variable': True, 'style_count': 33, 'tags': ['mono', 'sans']},
    {'provider_key': 'dinamo', 'family': 'Whyte', 'source_url': 'https://abcdinamo.com/typefaces/whyte', 'category': 'unknown', 'variable': True, 'style_count': 120, 'tags': ['display', 'mono', 'sans', 'semi-mono']},
    {'provider_key': 'displaay', 'family': 'Aguzzo', 'source_url': 'https://displaay.net/typeface/aguzzo', 'category': 'serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Avantt', 'source_url': 'https://displaay.net/typeface/avantt', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Bagoss', 'source_url': 'https://displaay.net/typeface/bagoss', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Booton', 'source_url': 'https://displaay.net/typeface/booton', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Cassette', 'source_url': 'https://displaay.net/typeface/cassette', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Concrette', 'source_url': 'https://displaay.net/typeface/concrette', 'category': 'serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Coolkit', 'source_url': 'https://displaay.net/typeface/coolkit', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Coxx', 'source_url': 'https://displaay.net/typeface/coxx', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Dazzed', 'source_url': 'https://displaay.net/typeface/dazzed', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Denim', 'source_url': 'https://displaay.net/typeface/denim', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Fellix', 'source_url': 'https://displaay.net/typeface/fellix', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Fenul', 'source_url': 'https://displaay.net/typeface/fenul', 'category': 'serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Gellix', 'source_url': 'https://displaay.net/typeface/gellix', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Greed', 'source_url': 'https://displaay.net/typeface/greed', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Haffer', 'source_url': 'https://displaay.net/typeface/haffer', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Hellix', 'source_url': 'https://displaay.net/typeface/hellix', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Jokker', 'source_url': 'https://displaay.net/typeface/jokker', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Lazzer', 'source_url': 'https://displaay.net/typeface/lazzer', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Matter', 'source_url': 'https://displaay.net/typeface/matter', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Ofform', 'source_url': 'https://displaay.net/typeface/ofform', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Panell', 'source_url': 'https://displaay.net/typeface/panell', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Perfektta', 'source_url': 'https://displaay.net/typeface/perfektta', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Post', 'source_url': 'https://displaay.net/typeface/post', 'category': 'serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Reckless', 'source_url': 'https://displaay.net/typeface/reckless', 'category': 'serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Roobert', 'source_url': 'https://displaay.net/typeface/roobert', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Saans', 'source_url': 'https://displaay.net/typeface/saans', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Season', 'source_url': 'https://displaay.net/typeface/season', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Serrif', 'source_url': 'https://displaay.net/typeface/serrif', 'category': 'serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Teodor', 'source_url': 'https://displaay.net/typeface/teodor', 'category': 'serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Tobias', 'source_url': 'https://displaay.net/typeface/tobias', 'category': 'serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Wallop', 'source_url': 'https://displaay.net/typeface/wallop', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'displaay', 'family': 'Yellix', 'source_url': 'https://displaay.net/typeface/yellix', 'category': 'sans-serif', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Alpina', 'source_url': 'https://www.grillitype.com/typeface/gt-alpina', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT America', 'source_url': 'https://www.grillitype.com/typeface/gt-america', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT America Intl', 'source_url': 'https://www.grillitype.com/typeface/gt-america-intl-collection', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Canon', 'source_url': 'https://www.grillitype.com/typeface/gt-canon', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Cinetype', 'source_url': 'https://www.grillitype.com/typeface/gt-cinetype', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Eesti', 'source_url': 'https://www.grillitype.com/typeface/gt-eesti', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Era', 'source_url': 'https://www.grillitype.com/typeface/gt-era', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Flaire', 'source_url': 'https://www.grillitype.com/typeface/gt-flaire', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Flexa', 'source_url': 'https://www.grillitype.com/typeface/gt-flexa', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Haptik', 'source_url': 'https://www.grillitype.com/typeface/gt-haptik', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Maru', 'source_url': 'https://www.grillitype.com/typeface/gt-maru', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Mechanik', 'source_url': 'https://www.grillitype.com/typeface/gt-mechanik', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Pantheon', 'source_url': 'https://www.grillitype.com/typeface/gt-pantheon', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Planar', 'source_url': 'https://www.grillitype.com/typeface/gt-planar', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Pressura', 'source_url': 'https://www.grillitype.com/typeface/gt-pressura', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Sectra', 'source_url': 'https://www.grillitype.com/typeface/gt-sectra', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Standard', 'source_url': 'https://www.grillitype.com/typeface/gt-standard', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Super', 'source_url': 'https://www.grillitype.com/typeface/gt-super', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Ultra', 'source_url': 'https://www.grillitype.com/typeface/gt-ultra', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Walsheim', 'source_url': 'https://www.grillitype.com/typeface/gt-walsheim', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'grilli-type', 'family': 'GT Zirkon', 'source_url': 'https://www.grillitype.com/typeface/gt-zirkon', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Calibre', 'source_url': 'https://klim.co.nz/fonts/calibre/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Die Grotesk', 'source_url': 'https://klim.co.nz/fonts/die-grotesk/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Domaine Display', 'source_url': 'https://klim.co.nz/fonts/domaine-display/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Domaine Sans Text', 'source_url': 'https://klim.co.nz/fonts/domaine-sans-text/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Domaine Text', 'source_url': 'https://klim.co.nz/fonts/domaine-text/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Epicene Display', 'source_url': 'https://klim.co.nz/fonts/epicene-display/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Epicene Text', 'source_url': 'https://klim.co.nz/fonts/epicene-text/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Family', 'source_url': 'https://klim.co.nz/fonts/family/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Feijoa', 'source_url': 'https://klim.co.nz/fonts/feijoa/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Financier Text', 'source_url': 'https://klim.co.nz/fonts/financier-text/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Founders Grotesk', 'source_url': 'https://klim.co.nz/fonts/founders-grotesk/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Founders Grotesk Mono', 'source_url': 'https://klim.co.nz/fonts/founders-grotesk-mono/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Geograph', 'source_url': 'https://klim.co.nz/fonts/geograph/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Heldane Text', 'source_url': 'https://klim.co.nz/fonts/heldane-text/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Karbon', 'source_url': 'https://klim.co.nz/fonts/karbon/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Maelstrom', 'source_url': 'https://klim.co.nz/fonts/maelstrom/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Martina Plantijn', 'source_url': 'https://klim.co.nz/fonts/martina-plantijn/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Metric', 'source_url': 'https://klim.co.nz/fonts/metric/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Mānuka', 'source_url': 'https://klim.co.nz/fonts/manuka/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'National 2', 'source_url': 'https://klim.co.nz/fonts/national-2/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Newzald', 'source_url': 'https://klim.co.nz/fonts/newzald/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Pitch', 'source_url': 'https://klim.co.nz/fonts/pitch/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Signifier', 'source_url': 'https://klim.co.nz/fonts/signifier/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Söhne', 'source_url': 'https://klim.co.nz/fonts/soehne/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Söhne Mono', 'source_url': 'https://klim.co.nz/fonts/soehne-mono/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'The Future', 'source_url': 'https://klim.co.nz/fonts/the-future/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Tiempos Headline', 'source_url': 'https://klim.co.nz/fonts/tiempos-headline/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Tiempos Text', 'source_url': 'https://klim.co.nz/fonts/tiempos-text/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Untitled Sans', 'source_url': 'https://klim.co.nz/fonts/untitled-sans/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'klim', 'family': 'Untitled Serif', 'source_url': 'https://klim.co.nz/fonts/untitled-serif/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Acma', 'source_url': 'https://pangrampangram.com/products/acma', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Agrandir', 'source_url': 'https://pangrampangram.com/products/agrandir', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Cirka', 'source_url': 'https://pangrampangram.com/products/cirka', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Editorial New', 'source_url': 'https://pangrampangram.com/products/editorial-new', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Editorial Old', 'source_url': 'https://pangrampangram.com/products/editorial-old', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Editorial Sans', 'source_url': 'https://pangrampangram.com/products/editorial-sans', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Eiko', 'source_url': 'https://pangrampangram.com/products/eiko', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Formula', 'source_url': 'https://pangrampangram.com/products/formula', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Fragment', 'source_url': 'https://pangrampangram.com/products/fragment', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Fraktion', 'source_url': 'https://pangrampangram.com/products/fraktion', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Frama', 'source_url': 'https://pangrampangram.com/products/frama', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Gatwick', 'source_url': 'https://pangrampangram.com/products/gatwick', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Gosha Sans', 'source_url': 'https://pangrampangram.com/products/gosha-sans', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Grafier', 'source_url': 'https://pangrampangram.com/products/grafier', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Hatton', 'source_url': 'https://pangrampangram.com/products/hatton', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Kyoto', 'source_url': 'https://pangrampangram.com/products/kyoto', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Lettra Mono', 'source_url': 'https://pangrampangram.com/products/lettra-mono', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Migra', 'source_url': 'https://pangrampangram.com/products/migra', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Model', 'source_url': 'https://pangrampangram.com/products/model', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Monument', 'source_url': 'https://pangrampangram.com/products/monument', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Mori', 'source_url': 'https://pangrampangram.com/products/mori', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Museum', 'source_url': 'https://pangrampangram.com/products/museum', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Neue Corp', 'source_url': 'https://pangrampangram.com/products/neue-corp', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Neue Gstaad', 'source_url': 'https://pangrampangram.com/products/neue-gstaad', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Neue Machina', 'source_url': 'https://pangrampangram.com/products/neue-machina-collection', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Neue Montreal', 'source_url': 'https://pangrampangram.com/products/neue-montreal', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Neue Montreal Arabic', 'source_url': 'https://pangrampangram.com/products/neue-montreal-arabic', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Neue Montreal Mono', 'source_url': 'https://pangrampangram.com/products/neue-montreal-mono', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Neue World', 'source_url': 'https://pangrampangram.com/products/neue-world', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Nikkei', 'source_url': 'https://pangrampangram.com/products/nikkei', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Object Sans', 'source_url': 'https://pangrampangram.com/products/object-sans', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Palma', 'source_url': 'https://pangrampangram.com/products/palma', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Pangaia', 'source_url': 'https://pangrampangram.com/products/pangaia', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Pangram Sans', 'source_url': 'https://pangrampangram.com/products/pangram-sans', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Rader', 'source_url': 'https://pangrampangram.com/products/rader', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Radio Grotesk', 'source_url': 'https://pangrampangram.com/products/radio-grotesk', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Right Didone', 'source_url': 'https://pangrampangram.com/products/right-didone', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Right Gothic', 'source_url': 'https://pangrampangram.com/products/right-gothic', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Right Grotesk', 'source_url': 'https://pangrampangram.com/products/right-grotesk', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Right Grotesk Mono', 'source_url': 'https://pangrampangram.com/products/right-grotesk-mono', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Right Sans', 'source_url': 'https://pangrampangram.com/products/right-sans', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Right Serif', 'source_url': 'https://pangrampangram.com/products/right-serif', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Right Serif Mono', 'source_url': 'https://pangrampangram.com/products/right-serif-mono', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Right Slab', 'source_url': 'https://pangrampangram.com/products/right-slab', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Supply', 'source_url': 'https://pangrampangram.com/products/supply', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Talisman', 'source_url': 'https://pangrampangram.com/products/talisman', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Telegraf', 'source_url': 'https://pangrampangram.com/products/telegraf', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Watch', 'source_url': 'https://pangrampangram.com/products/watch', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Woodland', 'source_url': 'https://pangrampangram.com/products/woodland', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'pangram-pangram', 'family': 'Writer', 'source_url': 'https://pangrampangram.com/products/writer', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'Black Mamba', 'source_url': 'https://www.swisstypefaces.com/fonts/black-mamba/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'BRRR', 'source_url': 'https://www.swisstypefaces.com/fonts/brrr/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'Euclid', 'source_url': 'https://www.swisstypefaces.com/fonts/euclid/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'Euclid Mono', 'source_url': 'https://www.swisstypefaces.com/fonts/euclid-mono/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'Euclid Stencil', 'source_url': 'https://www.swisstypefaces.com/fonts/euclid-stencil/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'IKANSEEYOUALL', 'source_url': 'https://www.swisstypefaces.com/fonts/ikanseeyouall/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'KOPYME', 'source_url': 'https://www.swisstypefaces.com/fonts/kopy-me/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'KRSNA', 'source_url': 'https://www.swisstypefaces.com/fonts/krsna/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'NewPanam', 'source_url': 'https://www.swisstypefaces.com/fonts/newpanam/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'NewParis', 'source_url': 'https://www.swisstypefaces.com/fonts/newparis/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'Only', 'source_url': 'https://www.swisstypefaces.com/fonts/only-extended/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'Raskal Oner', 'source_url': 'https://www.swisstypefaces.com/fonts/raskal-oner/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'Riviera', 'source_url': 'https://www.swisstypefaces.com/fonts/riviera/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'SangBleu', 'source_url': 'https://www.swisstypefaces.com/fonts/sangbleu/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'SangBleu OG', 'source_url': 'https://www.swisstypefaces.com/fonts/sangbleu-og/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'Simplon', 'source_url': 'https://www.swisstypefaces.com/fonts/simplon/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'Suisse', 'source_url': 'https://www.swisstypefaces.com/fonts/suisse/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'TheW', 'source_url': 'https://www.swisstypefaces.com/fonts/thew/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
    {'provider_key': 'swiss-typefaces', 'family': 'Vogy Smog', 'source_url': 'https://www.swisstypefaces.com/fonts/vogy/', 'category': 'unknown', 'variable': None, 'style_count': None, 'tags': []},
]


def slug(value: str) -> str:
    folded = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    result = re.sub(r'[^a-z0-9]+', '-', folded).strip('-')
    if not result:
        raise ValueError('Family identifiers require a nonempty slug')
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(metadata_path: Path, tree_path: Path, commit: str, retrieved_at: str,
          acquisition_manifest: Path | None = None) -> dict:
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected a full lowercase Git commit SHA')
    datetime.fromisoformat(retrieved_at.replace('Z', '+00:00'))
    metadata = json.loads(metadata_path.read_text(encoding='utf-8').removeprefix(")]}'\n"))
    tree = json.loads(tree_path.read_text(encoding='utf-8'))
    if tree.get('truncated') is not False:
        raise ValueError('A complete, untruncated Git tree is required')
    by_slug = {}
    by_path = {row['path']: row for row in tree['tree']}
    for row in tree['tree']:
        parts = row['path'].split('/')
        if len(parts) == 3 and parts[-1] == 'METADATA.pb' and parts[0] in {'ofl', 'apache', 'ufl'}:
            if parts[1] in by_slug:
                raise ValueError(f'Ambiguous Google family directory: {parts[1]}')
            by_slug[parts[1]] = '/'.join(parts[:2])
    acquisition_by_path = {}
    if acquisition_manifest is not None:
        acquisition = json.loads(acquisition_manifest.read_text(encoding='utf-8'))
        if acquisition['collection']['commit'] != commit:
            raise ValueError('Acquisition manifest and directory commit differ')
        if acquisition['collection']['family_metadata_sha256'] != digest(metadata_path):
            raise ValueError('Acquisition manifest and directory metadata snapshots differ')
        acquisition_by_path = {row['path']: row for row in acquisition['families']}
    license_labels = {'ofl': 'SIL Open Font License 1.1', 'apache': 'Apache License 2.0',
                      'ufl': 'Ubuntu Font License 1.0'}
    families = []
    unmatched = []
    for raw in metadata['familyMetadataList']:
        family = raw['family']
        directory_slug = slug(family).replace('-', '')
        source_path = by_slug.get(directory_slug)
        path_license = source_path.split('/')[0] if source_path else None
        style_names = sorted(raw.get('fonts', {}), key=lambda value: (int(value.rstrip('i')), value.endswith('i')))
        axes = raw.get('axes', [])
        category = raw['category'].lower().replace(' ', '-')
        tags = {category, *(item.lower().replace(' ', '-') for item in raw.get('classifications', []))}
        subsets = sorted(set(raw.get('subsets', [])) - {'menu'})
        if axes:
            tags.add('variable')
        if raw.get('colorCapabilities'):
            tags.add('color')
        designers = raw.get('designers', [])
        license_paths = [source_path + '/' + name for name in ('OFL.txt', 'LICENSE.txt', 'UFL.txt')
                         if source_path and source_path + '/' + name in by_path]
        acquisition_row = acquisition_by_path.get(source_path)
        if source_path is None:
            unmatched.append(family)
        specimen_url = 'https://fonts.google.com/specimen/' + quote(family, safe='').replace('%20', '+')
        source_url = ('https://github.com/google/fonts/tree/' + commit + '/' + source_path
                      if source_path else specimen_url)
        reason = ('pinned-source-available' if acquisition_row else
                  'family-not-in-pinned-repository' if source_path is None else
                  'family-license-file-not-pinned' if not license_paths else
                  'acquisition-manifest-not-supplied')
        families.append({
            'id': 'directory:google-fonts:' + slug(family), 'family': family,
            'provider': 'Google Fonts', 'vendor': ', '.join(designers) or None,
            'category': category, 'category_source': 'Google Fonts metadata',
            'license_kind': 'open' if raw.get('isOpenSource') is True else 'unknown',
            'license_label': license_labels.get(path_license, 'Open source declared by Google Fonts; specific license not pinned'),
            'license_url': 'https://github.com/google/fonts/blob/' + commit + '/' + license_paths[0] if license_paths else None,
            'source_url': source_url, 'source_path': source_path,
            'acquisition_url': specimen_url, 'specimen_url': specimen_url,
            'access': 'open-download', 'tags': sorted(tags), 'variable': bool(axes),
            'styles': style_names, 'style_count': len(style_names), 'subsets': subsets,
            'axes': axes, 'designers': designers,
            'last_modified': raw.get('lastModified'),
            'preview': {'type': 'google-fonts', 'family': family},
            'acquisition': {'mode': 'pinned-source' if acquisition_row else 'provider-link',
                            'available': acquisition_row is not None,
                            'source_id': acquisition_row['id'] if acquisition_row else None,
                            'reason': reason},
            'indexed': False, 'renderable': False, 'local_availability': 'not-checked',
            'provenance': {'source_id': 'google-fonts-metadata', 'retrieved_at': retrieved_at,
                           'repository_commit': commit if source_path else None,
                           'metadata_scope': 'provider-declared; no binary inspection'},
        })
    commercial_sources = {source['id']: source for source in COMMERCIAL_SOURCES}
    for item in COMMERCIAL_FAMILIES:
        source = commercial_sources[item['provider_key']]
        tags = set(item['tags'])
        if item['category'] != 'unknown':
            tags.add(item['category'])
        if item['variable'] is True:
            tags.add('variable')
        families.append({
            'id': 'directory:' + item['provider_key'] + ':' + slug(item['family']),
            'family': item['family'], 'provider': source['provider'], 'vendor': source['provider'],
            'category': item['category'],
            'category_source': 'official foundry catalog' if item['category'] != 'unknown' else None,
            'license_kind': 'commercial', 'license_label': 'Proprietary; obtain the appropriate foundry license',
            'license_url': source['license_url'], 'source_url': item['source_url'],
            'source_path': None, 'acquisition_url': item['source_url'],
            'specimen_url': item['source_url'], 'access': 'commercial-license',
            'tags': sorted(tags), 'variable': item['variable'], 'styles': [],
            'style_count': item['style_count'], 'subsets': [], 'axes': [], 'designers': [],
            'last_modified': None, 'preview': {'type': 'provider-only', 'family': item['family']},
            'acquisition': {'mode': 'provider-link', 'available': False, 'source_id': None,
                            'reason': 'license-and-import-authorized-local-files'},
            'indexed': False, 'renderable': False, 'local_availability': 'not-checked',
            'provenance': {'source_id': item['provider_key'], 'retrieved_at': source['retrieved_at'],
                           'repository_commit': None,
                           'metadata_scope': 'selected official retail listing; may group subfamilies'},
        })
    families.sort(key=lambda row: (row['family'].casefold(), row['id']))
    if len({row['id'] for row in families}) != len(families):
        raise ValueError('Duplicate family identifiers')
    for row in families:
        for field in ('source_url', 'acquisition_url', 'specimen_url', 'license_url'):
            if row[field] is not None and urlparse(row[field]).scheme != 'https':
                raise ValueError(f'Non-HTTPS {field} in {row["id"]}')
    metadata_source = {'id': 'google-fonts-metadata', 'provider': 'Google Fonts',
                       'url': 'https://fonts.google.com/metadata/fonts',
                       'retrieved_at': retrieved_at, 'sha256': digest(metadata_path),
                       'kind': 'official-live-catalog-metadata'}
    tree_source = {'id': 'google-fonts-repository', 'provider': 'Google Fonts',
                  'url': 'https://github.com/google/fonts/tree/' + commit,
                  'retrieved_at': retrieved_at, 'sha256': digest(tree_path),
                  'kind': 'pinned-git-tree', 'commit': commit,
                  'family_directories': len(by_slug), 'truncated': False}
    return {
        'schema_version': 1,
        'snapshot': {
            'retrieved_at': retrieved_at,
            'google_served_families': len(metadata['familyMetadataList']),
            'google_repository_family_directories': len(by_slug),
            'google_families_without_repository_match': unmatched,
            'google_families_with_pinned_acquisition': sum(r['acquisition']['available'] for r in families),
            'commercial_listings': len(COMMERCIAL_FAMILIES),
            'sources': [metadata_source, tree_source, *COMMERCIAL_SOURCES],
            'scope': 'Dated discovery metadata. Provider listings may be families, subfamilies, or collections; not a count of local exact faces.',
        },
        'families': families,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata', type=Path, required=True, help='Saved Google Fonts metadata JSON')
    parser.add_argument('--tree', type=Path, required=True, help='Saved untruncated google/fonts Git tree JSON')
    parser.add_argument('--commit', required=True, help='Full verified commit corresponding to --tree')
    parser.add_argument('--retrieved-at', required=True, help='Actual metadata retrieval time in ISO 8601')
    parser.add_argument('--acquisition-manifest', type=Path, help='Matching source-packs.json enables pinned acquisition links')
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parents[1] / 'type_evidence' / 'font_directory.json')
    args = parser.parse_args()
    data = build(args.metadata, args.tree, args.commit, args.retrieved_at, args.acquisition_manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print(json.dumps({'families': len(data['families']), 'output': str(args.out), 'sha256': digest(args.out)}))


if __name__ == '__main__':
    main()
