# Copyright (C) 2013 eNovance SAS <licensing@enovance.com>
#
# Author: Sylvain Afchain <sylvain.afchain@enovance.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import contextlib
import logging

import webob.exc

from neutron.api.extensions import ExtensionMiddleware
from neutron.api.extensions import PluginAwareExtensionManager
from neutron.common import config
from neutron import context
import neutron.extensions
from neutron.extensions import metering
from neutron.plugins.common import constants
from neutron.services.metering import metering_plugin
from neutron.tests.unit import test_db_plugin

LOG = logging.getLogger(__name__)

DB_METERING_PLUGIN_KLASS = (
    "neutron.services.metering."
    "metering_plugin.MeteringPlugin"
)

extensions_path = ':'.join(neutron.extensions.__path__)


class MeteringPluginDbTestCaseMixin(object):
    def _create_metering_label(self, fmt, name, description, **kwargs):
        data = {'metering_label': {'name': name,
                                   'tenant_id': kwargs.get('tenant_id',
                                                           'test_tenant'),
                                   'description': description}}
        req = self.new_create_request('metering-labels', data,
                                      fmt)

        if kwargs.get('set_context') and 'tenant_id' in kwargs:
            # create a specific auth context for this request
            req.environ['neutron.context'] = (
                context.Context('', kwargs['tenant_id'],
                                is_admin=kwargs.get('is_admin', True)))

        return req.get_response(self.ext_api)

    def _make_metering_label(self, fmt, name, description, **kwargs):
        res = self._create_metering_label(fmt, name, description, **kwargs)
        if res.status_int >= 400:
            raise webob.exc.HTTPClientError(code=res.status_int)
        return self.deserialize(fmt, res)

    def _create_metering_label_rule(self, fmt, metering_label_id, direction,
                                    remote_ip_prefix, excluded, **kwargs):
        data = {'metering_label_rule':
                {'metering_label_id': metering_label_id,
                 'tenant_id': kwargs.get('tenant_id', 'test_tenant'),
                 'direction': direction,
                 'excluded': excluded,
                 'remote_ip_prefix': remote_ip_prefix}}
        req = self.new_create_request('metering-label-rules',
                                      data, fmt)

        if kwargs.get('set_context') and 'tenant_id' in kwargs:
            # create a specific auth context for this request
            req.environ['neutron.context'] = (
                context.Context('', kwargs['tenant_id']))

        return req.get_response(self.ext_api)

    def _make_metering_label_rule(self, fmt, metering_label_id, direction,
                                  remote_ip_prefix, excluded, **kwargs):
        res = self._create_metering_label_rule(fmt, metering_label_id,
                                               direction, remote_ip_prefix,
                                               excluded, **kwargs)
        if res.status_int >= 400:
            raise webob.exc.HTTPClientError(code=res.status_int)
        return self.deserialize(fmt, res)

    @contextlib.contextmanager
    def metering_label(self, name='label', description='desc',
                       fmt=None, no_delete=False, **kwargs):
        if not fmt:
            fmt = self.fmt
        metering_label = self._make_metering_label(fmt, name,
                                                   description, **kwargs)
        yield metering_label
        if not no_delete:
            self._delete('metering-labels',
                         metering_label['metering_label']['id'])

    @contextlib.contextmanager
    def metering_label_rule(self, metering_label_id=None, direction='ingress',
                            remote_ip_prefix='10.0.0.0/24',
                            excluded='false', fmt=None, no_delete=False):
        if not fmt:
            fmt = self.fmt
        metering_label_rule = self._make_metering_label_rule(fmt,
                                                             metering_label_id,
                                                             direction,
                                                             remote_ip_prefix,
                                                             excluded)
        yield metering_label_rule
        if not no_delete:
            self._delete('metering-label-rules',
                         metering_label_rule['metering_label_rule']['id'])


class MeteringPluginDbTestCase(test_db_plugin.NeutronDbPluginV2TestCase,
                               MeteringPluginDbTestCaseMixin):
    fmt = 'json'

    resource_prefix_map = dict(
        (k.replace('_', '-'), constants.COMMON_PREFIXES[constants.METERING])
        for k in metering.RESOURCE_ATTRIBUTE_MAP.keys()
    )

    def setUp(self, plugin=None):
        service_plugins = {'metering_plugin_name': DB_METERING_PLUGIN_KLASS}

        super(MeteringPluginDbTestCase, self).setUp(
            plugin=plugin,
            service_plugins=service_plugins
        )

        self.plugin = metering_plugin.MeteringPlugin()
        ext_mgr = PluginAwareExtensionManager(
            extensions_path,
            {constants.METERING: self.plugin}
        )
        app = config.load_paste_app('extensions_test_app')
        self.ext_api = ExtensionMiddleware(app, ext_mgr=ext_mgr)

    def test_create_metering_label(self):
        name = 'my label'
        description = 'my metering label'
        keys = [('name', name,), ('description', description)]
        with self.metering_label(name, description) as metering_label:
            for k, v, in keys:
                self.assertEqual(metering_label['metering_label'][k], v)

    def test_delete_metering_label(self):
        name = 'my label'
        description = 'my metering label'

        with self.metering_label(name, description,
                                 no_delete=True) as metering_label:
            metering_label_id = metering_label['metering_label']['id']
            self._delete('metering-labels', metering_label_id, 204)

    def test_list_metering_label(self):
        name = 'my label'
        description = 'my metering label'

        with contextlib.nested(
                self.metering_label(name, description),
                self.metering_label(name, description)) as metering_label:

            self._test_list_resources('metering-label', metering_label)

    def test_create_metering_label_rule(self):
        name = 'my label'
        description = 'my metering label'

        with self.metering_label(name, description) as metering_label:
            metering_label_id = metering_label['metering_label']['id']

            direction = 'egress'
            remote_ip_prefix = '192.168.0.0/24'
            excluded = True

            keys = [('metering_label_id', metering_label_id),
                    ('direction', direction),
                    ('excluded', excluded),
                    ('remote_ip_prefix', remote_ip_prefix)]
            with self.metering_label_rule(metering_label_id,
                                          direction,
                                          remote_ip_prefix,
                                          excluded) as label_rule:
                for k, v, in keys:
                    self.assertEqual(label_rule['metering_label_rule'][k], v)

    def test_delete_metering_label_rule(self):
        name = 'my label'
        description = 'my metering label'

        with self.metering_label(name, description) as metering_label:
            metering_label_id = metering_label['metering_label']['id']

            direction = 'egress'
            remote_ip_prefix = '192.168.0.0/24'
            excluded = True

            with self.metering_label_rule(metering_label_id,
                                          direction,
                                          remote_ip_prefix,
                                          excluded,
                                          no_delete=True) as label_rule:
                rule_id = label_rule['metering_label_rule']['id']
                self._delete('metering-label-rules', rule_id, 204)

    def test_list_metering_label_rule(self):
        name = 'my label'
        description = 'my metering label'

        with self.metering_label(name, description) as metering_label:
            metering_label_id = metering_label['metering_label']['id']

            direction = 'egress'
            remote_ip_prefix = '192.168.0.0/24'
            excluded = True

            with contextlib.nested(
                self.metering_label_rule(metering_label_id,
                                         direction,
                                         remote_ip_prefix,
                                         excluded),
                self.metering_label_rule(metering_label_id,
                                         'ingress',
                                         remote_ip_prefix,
                                         excluded)) as metering_label_rule:

                self._test_list_resources('metering-label-rule',
                                          metering_label_rule)

    def test_create_metering_label_rules(self):
        name = 'my label'
        description = 'my metering label'

        with self.metering_label(name, description) as metering_label:
            metering_label_id = metering_label['metering_label']['id']

            direction = 'egress'
            remote_ip_prefix = '192.168.0.0/24'
            excluded = True

            with contextlib.nested(
                self.metering_label_rule(metering_label_id,
                                         direction,
                                         remote_ip_prefix,
                                         excluded),
                self.metering_label_rule(metering_label_id,
                                         direction,
                                         '0.0.0.0/0',
                                         False)) as metering_label_rule:

                self._test_list_resources('metering-label-rule',
                                          metering_label_rule)

    def test_create_metering_label_rule_two_labels(self):
        name1 = 'my label 1'
        name2 = 'my label 2'
        description = 'my metering label'

        with self.metering_label(name1, description) as metering_label1:
            metering_label_id1 = metering_label1['metering_label']['id']

            with self.metering_label(name2, description) as metering_label2:
                metering_label_id2 = metering_label2['metering_label']['id']

                direction = 'egress'
                remote_ip_prefix = '192.168.0.0/24'
                excluded = True

                with contextlib.nested(
                    self.metering_label_rule(metering_label_id1,
                                             direction,
                                             remote_ip_prefix,
                                             excluded),
                    self.metering_label_rule(metering_label_id2,
                                             direction,
                                             remote_ip_prefix,
                                             excluded)) as metering_label_rule:

                    self._test_list_resources('metering-label-rule',
                                              metering_label_rule)


class TestMeteringDbXML(MeteringPluginDbTestCase):
    fmt = 'xml'
