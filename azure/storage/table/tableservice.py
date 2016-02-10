﻿#-------------------------------------------------------------------------
# Copyright (c) Microsoft.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#--------------------------------------------------------------------------
from contextlib import contextmanager
from azure.common import (
    AzureHttpError,
)
from .._common_conversion import (
    _int_or_none,
    _str,
    _str_or_none,
)
from .._error import (
    _dont_fail_not_exist,
    _dont_fail_on_exist,
    _validate_not_none,
    _ERROR_STORAGE_MISSING_INFO,
)
from .._serialization import (
    _get_request_body,
    _update_request,
    _convert_signed_identifiers_to_xml,
    _convert_service_properties_to_xml,
)
from .._http import HTTPRequest
from ..models import (
    Services,
    ListGenerator,
)
from .models import TablePayloadFormat
from .._auth import (
    _StorageSASAuthentication,
    _StorageTableSharedKeyAuthentication,
)
from .._connection import _ServiceParameters
from .._deserialization import (
    _convert_xml_to_service_properties,
    _convert_xml_to_signed_identifiers,
)
from ._serialization import (
    _convert_table_to_json,
    _convert_batch_to_json,
    _update_storage_table_header,
    _get_entity_path,
    _DEFAULT_ACCEPT_HEADER,
    _DEFAULT_CONTENT_TYPE_HEADER,
    _DEFAULT_PREFER_HEADER,
)
from ._deserialization import (
    _convert_json_response_to_entity,
    _convert_json_response_to_tables,
    _convert_json_response_to_entities,
    _parse_batch_response,
    _extract_etag,
)
from .._constants import (
    SERVICE_HOST_BASE,
    DEFAULT_PROTOCOL,
)
from ._request import (
    _get_entity,
    _insert_entity,
    _update_entity,
    _merge_entity,
    _delete_entity,
    _insert_or_replace_entity,
    _insert_or_merge_entity,
)
from ..sharedaccesssignature import (
    SharedAccessSignature,
)
from ..storageclient import StorageClient
from .tablebatch import TableBatch

class TableService(StorageClient):

    '''
    This is the main class managing Azure Table resources.

    The Azure Table service offers structured storage in the form of tables. Tables 
    store data as collections of entities. Entities are similar to rows. An entity 
    has a primary key and a set of properties. A property is a name, typed-value pair, 
    similar to a column. The Table service does not enforce any schema for tables, 
    so two entities in the same table may have different sets of properties. Developers 
    may choose to enforce a schema on the client side. A table may contain any number 
    of entities.
    '''

    def __init__(self, account_name=None, account_key=None, sas_token=None, 
                 is_emulated=False, protocol=DEFAULT_PROTOCOL, endpoint_suffix=SERVICE_HOST_BASE,
                 request_session=None, connection_string=None):
        '''
        :param str account_name:
            The storage account name. This is used to authenticate requests 
            signed with an account key and to construct the storage endpoint. It 
            is required unless a connection string is given.
        :param str account_key:
            The storage account key. This is used for shared key authentication. 
        :param str sas_token:
             A shared access signature token to use to authenticate requests 
             instead of the account key. If account key and sas token are both 
             specified, account key will be used to sign.
        :param bool is_emulated:
            Whether to use the emulator. Defaults to False. If specified, will 
            override all other parameters besides connection string and request 
            session.
        :param str protocol:
            The protocol to use for requests. Defaults to https.
        :param str endpoint_suffix:
            The host base component of the url, minus the account name. Defaults 
            to Azure (core.windows.net). Override this to use the China cloud 
            (core.chinacloudapi.cn).
        :param requests.Session request_session:
            The session object to use for http requests.
        :param str connection_string:
            If specified, this will override all other parameters besides 
            request session. See
            http://azure.microsoft.com/en-us/documentation/articles/storage-configure-connection-string/
            for the connection string format.
        '''
        service_params = _ServiceParameters.get_service_parameters(
            'table',
            account_name=account_name, 
            account_key=account_key, 
            sas_token=sas_token, 
            is_emulated=is_emulated, 
            protocol=protocol, 
            endpoint_suffix=endpoint_suffix,
            request_session=request_session,
            connection_string=connection_string)
            
        super(TableService, self).__init__(service_params)

        if self.account_key:
            self.authentication = _StorageTableSharedKeyAuthentication(
                self.account_name,
                self.account_key,
            )
        elif self.sas_token:
            self.authentication = _StorageSASAuthentication(self.sas_token)
        else:
            raise ValueError(_ERROR_STORAGE_MISSING_INFO)


    def generate_account_shared_access_signature(self, resource_types, permission, 
                                        expiry, start=None, ip=None, protocol=None):
        '''
        Generates a shared access signature for the table service.
        Use the returned signature with the sas_token parameter of TableService.

        :param ResourceTypes resource_types:
            Specifies the resource types that are accessible with the account SAS.
        :param AccountPermissions permission:
            The permissions associated with the shared access signature. The 
            user is restricted to operations allowed by the permissions. 
            Required unless an id is given referencing a stored access policy 
            which contains this field. This field must be omitted if it has been 
            specified in an associated stored access policy.
        :param expiry:
            The time at which the shared access signature becomes invalid. 
            Required unless an id is given referencing a stored access policy 
            which contains this field. This field must be omitted if it has 
            been specified in an associated stored access policy. Azure will always 
            convert values to UTC. If a date is passed in without timezone info, it 
            is assumed to be UTC.
        :type expiry: date or str
        :param start:
            The time at which the shared access signature becomes valid. If 
            omitted, start time for this call is assumed to be the time when the 
            storage service receives the request. Azure will always convert values 
            to UTC. If a date is passed in without timezone info, it is assumed to 
            be UTC.
        :type start: date or str
        :param str ip:
            Specifies an IP address or a range of IP addresses from which to accept requests.
            If the IP address from which the request originates does not match the IP address
            or address range specified on the SAS token, the request is not authenticated.
            For example, specifying sip=168.1.5.65 or sip=168.1.5.60-168.1.5.70 on the SAS
            restricts the request to those IP addresses.
        :param str protocol:
            Specifies the protocol permitted for a request made. The default value
            is https,http. See :class:`~azure.storage.models.Protocol` for possible values.
        :return: A Shared Access Signature (sas) token.
        :rtype: str
        '''
        _validate_not_none('self.account_name', self.account_name)
        _validate_not_none('self.account_key', self.account_key)

        sas = SharedAccessSignature(self.account_name, self.account_key)
        return sas.generate_account(Services.TABLE, resource_types, permission, 
                                    expiry, start=start, ip=ip, protocol=protocol)


    def generate_table_shared_access_signature(self, table_name, permission=None, 
                                        expiry=None, start=None, id=None,
                                        ip=None, protocol=None,
                                        start_pk=None, start_rk=None, 
                                        end_pk=None, end_rk=None):
        '''
        Generates a shared access signature for the table.
        Use the returned signature with the sas_token parameter of TableService.

        :param str table_name:
            The name of the table to create a SAS token for.
        :param TablePermissions permission:
            The permissions associated with the shared access signature. The 
            user is restricted to operations allowed by the permissions. 
            Required unless an id is given referencing a stored access policy 
            which contains this field. This field must be omitted if it has been 
            specified in an associated stored access policy.
        :param expiry:
            The time at which the shared access signature becomes invalid. 
            Required unless an id is given referencing a stored access policy 
            which contains this field. This field must be omitted if it has 
            been specified in an associated stored access policy. Azure will always 
            convert values to UTC. If a date is passed in without timezone info, it 
            is assumed to be UTC.
        :type expiry: date or str
        :param start:
            The time at which the shared access signature becomes valid. If 
            omitted, start time for this call is assumed to be the time when the 
            storage service receives the request. Azure will always convert values 
            to UTC. If a date is passed in without timezone info, it is assumed to 
            be UTC.
        :type start: date or str
        :param str id:
            A unique value up to 64 characters in length that correlates to a 
            stored access policy. To create a stored access policy, use :func:`~set_table_acl`.
        :param str ip:
            Specifies an IP address or a range of IP addresses from which to accept requests.
            If the IP address from which the request originates does not match the IP address
            or address range specified on the SAS token, the request is not authenticated.
            For example, specifying sip='168.1.5.65' or sip='168.1.5.60-168.1.5.70' on the SAS
            restricts the request to those IP addresses.
        :param str protocol:
            Specifies the protocol permitted for a request made. The default value
            is https,http. See :class:`~azure.storage.models.Protocol` for possible values.
        :param str start_pk:
            The minimum partition key accessible with this shared access 
            signature. startpk must accompany startrk. Key values are inclusive. 
            If omitted, there is no lower bound on the table entities that can 
            be accessed.
        :param str start_rk:
            The minimum row key accessible with this shared access signature. 
            startpk must accompany startrk. Key values are inclusive. If 
            omitted, there is no lower bound on the table entities that can be 
            accessed.
        :param str end_pk:
            The maximum partition key accessible with this shared access 
            signature. endpk must accompany endrk. Key values are inclusive. If 
            omitted, there is no upper bound on the table entities that can be 
            accessed.
        :param str end_rk:
            The maximum row key accessible with this shared access signature. 
            endpk must accompany endrk. Key values are inclusive. If omitted, 
            there is no upper bound on the table entities that can be accessed.
        :return: A Shared Access Signature (sas) token.
        :rtype: str
        '''
        _validate_not_none('table_name', table_name)
        _validate_not_none('self.account_name', self.account_name)
        _validate_not_none('self.account_key', self.account_key)

        sas = SharedAccessSignature(self.account_name, self.account_key)
        return sas.generate_table(
            table_name,
            permission=permission, 
            expiry=expiry,
            start=start, 
            id=id,
            ip=ip,
            protocol=protocol,
            start_pk=start_pk,
            start_rk=start_rk,
            end_pk=end_pk,
            end_rk=end_rk,
        )

    def get_table_service_properties(self, timeout=None):
        '''
        Gets the properties of a storage account's Table service, including
        logging, analytics and CORS rules.

        :param int timeout:
            The server timeout, expressed in seconds.
        :return: The table service properties.
        :rtype: :class:`~azure.storage.models.ServiceProperties`
        '''
        request = HTTPRequest()
        request.method = 'GET'
        request.host = self._get_host()
        request.path = '/'
        request.query = [
            ('restype', 'service'),
            ('comp', 'properties'),
            ('timeout', _int_or_none(timeout)),
        ]

        response = self._perform_request(request)
        return _convert_xml_to_service_properties(response.body)

    def set_table_service_properties(self, logging=None, hour_metrics=None, 
                                    minute_metrics=None, cors=None, timeout=None):
        '''
        Sets the properties of a storage account's Table service, including
        Azure Storage Analytics. If an element (ex Logging) is left as None, the 
        existing settings on the service for that functionality are preserved. 
        For more information on Azure Storage Analytics, see 
        https://msdn.microsoft.com/en-us/library/azure/hh343270.aspx.

        :param Logging logging:
            The logging settings provide request logs.
        :param Metrics hour_metrics:
            The hour metrics settings provide a summary of request 
            statistics grouped by API in hourly aggregates for blobs.
        :param Metrics minute_metrics:
            The minute metrics settings provide request statistics 
            for each minute for blobs.
        :param cors:
            You can include up to five CorsRule elements in the 
            list. If an empty list is specified, all CORS rules will be deleted, 
            and CORS will be disabled for the service. For detailed information 
            about CORS rules and evaluation logic, see 
            https://msdn.microsoft.com/en-us/library/azure/dn535601.aspx.
        :type cors: list of :class:`~azure.storage.models.CorsRule`
        :param int timeout:
            The server timeout, expressed in seconds.
        '''
        request = HTTPRequest()
        request.method = 'PUT'
        request.host = self._get_host()
        request.path = '/'
        request.query = [
            ('restype', 'service'),
            ('comp', 'properties'),
            ('timeout', _int_or_none(timeout)),
        ]
        request.body = _get_request_body(
            _convert_service_properties_to_xml(logging, hour_metrics, minute_metrics, cors))

        self._perform_request(request)

    def list_tables(self, max_results=None, marker=None, timeout=None):
        '''
        Returns a generator to list the tables. The generator will lazily follow 
        the continuation tokens returned by the service and stop when all tables 
        have been returned or max_results is reached.

        If max_results is specified and the account has more than that number of 
        tables, the generator will have a populated next_marker field once it 
        finishes. This marker can be used to create a new generator if more 
        results are desired.

        :param int max_results:
            The maximum number of tables to return.
        :param marker:
            An opaque continuation object. This value can be retrieved from the 
            next_marker field of a previous generator object if max_results was 
            specified and that generator has finished enumerating results. If 
            specified, this generator will begin returning results from the point 
            where the previous generator stopped.
        :type marker: obj
        :param int timeout:
            The server timeout, expressed in seconds. This function may make multiple 
            calls to the service in which case the timeout value specified will be 
            applied to each individual call.
        :return: A generator which produces :class:`~azure.storage.models.table.Table` objects.
        :rtype: :class:`~azure.storage.models.ListGenerator`:
        '''
        kwargs = {'max_results': max_results, 'marker': marker, 'timeout': timeout}
        resp = self._list_tables(**kwargs)

        return ListGenerator(resp, self._list_tables, (), kwargs)

    def _list_tables(self, max_results=None, marker=None, timeout=None):
        '''
        Returns a list of tables under the specified account. Makes a single list 
        request to the service. Used internally by the list_tables method.

        :param int max_results:
            The maximum number of tables to return. A single list request may 
            return up to 1000 tables and potentially a continuation token which 
            should be followed to get additional resutls.
        :param marker:
            A dictionary which identifies the portion of the query to be
            returned with the next query operation. The operation returns a
            next_marker element within the response body if the list returned
            was not complete. This value may then be used as a query parameter
            in a subsequent call to request the next portion of the list of
            queues. The marker value is opaque to the client.
        :type marker: obj
        :param int timeout:
            The server timeout, expressed in seconds.
        :return: A list of tables, potentially with a next_marker property.
        :rtype: list of :class:`~azure.storage.models.table.Table`:  
        '''
        request = HTTPRequest()
        request.method = 'GET'
        request.host = self._get_host()
        request.path = '/Tables'
        request.headers = [('Accept', TablePayloadFormat.JSON_NO_METADATA)]
        request.query = [
            ('$top', _int_or_none(max_results)),
            ('NextTableName', _str_or_none(marker)),
            ('timeout', _int_or_none(timeout)),
        ]

        response = self._perform_request(request)
        return _convert_json_response_to_tables(response)

    def create_table(self, table_name, fail_on_exist=False, timeout=None):
        '''
        Creates a new table in the storage account.

        :param str table_name:
            The name of the table to create. The table name may contain only
            alphanumeric characters and cannot begin with a numeric character.
            It is case-insensitive and must be from 3 to 63 characters long.
        :param bool fail_on_exist:
            Specifies whether to throw an exception if the table already exists.
        :param int timeout:
            The server timeout, expressed in seconds.
        :return:
            A boolean indicating whether the table was created. If fail_on_exist 
            was set to True, this will throw instead of returning false.
        :rtype: bool
        '''
        _validate_not_none('table', table_name)
        request = HTTPRequest()
        request.method = 'POST'
        request.host = self._get_host()
        request.path = '/Tables'
        request.query = [('timeout', _int_or_none(timeout))]
        request.headers = [_DEFAULT_CONTENT_TYPE_HEADER,
                           _DEFAULT_PREFER_HEADER,
                           _DEFAULT_ACCEPT_HEADER]
        request.body = _get_request_body(_convert_table_to_json(table_name))

        if not fail_on_exist:
            try:
                self._perform_request(request)
                return True
            except AzureHttpError as ex:
                _dont_fail_on_exist(ex)
                return False
        else:
            self._perform_request(request)
            return True

    def exists(self, table_name, timeout=None):
        '''
        Returns a boolean indicating whether the table exists.

        :param str table_name:
            The name of table to check for existence.
        :param int timeout:
            The server timeout, expressed in seconds.
        :return: A boolean indicating whether the table exists.
        :rtype: bool
        '''
        _validate_not_none('table_name', table_name)
        request = HTTPRequest()
        request.method = 'GET'
        request.host = self._get_host()
        request.path = '/Tables' + "('" + table_name + "')"
        request.headers = [('Accept', TablePayloadFormat.JSON_NO_METADATA)]
        request.query = [('timeout', _int_or_none(timeout))]

        try:
            self._perform_request(request)
            return True
        except AzureHttpError as ex:
            _dont_fail_not_exist(ex)
            return False

    def delete_table(self, table_name, fail_not_exist=False, timeout=None):
        '''
        Deletes the specified table and any data it contains.

        When a table is successfully deleted, it is immediately marked for deletion 
        and is no longer accessible to clients. The table is later removed from 
        the Table service during garbage collection.

        Note that deleting a table is likely to take at least 40 seconds to complete. 
        If an operation is attempted against the table while it was being deleted, 
        an :class:`AzureConflictHttpError` will be thrown.

        :param str table_name:
            The name of the table to delete.
        :param bool fail_not_exist:
            Specifies whether to throw an exception if the table doesn't exist.
        :param int timeout:
            The server timeout, expressed in seconds.
        :return:
            A boolean indicating whether the table was deleted. If fail_not_exist 
            was set to True, this will throw instead of returning false.
        :rtype: bool
        '''
        _validate_not_none('table_name', table_name)
        request = HTTPRequest()
        request.method = 'DELETE'
        request.host = self._get_host()
        request.path = '/Tables(\'' + _str(table_name) + '\')'
        request.query = [('timeout', _int_or_none(timeout))]
        request.headers = [_DEFAULT_ACCEPT_HEADER]

        if not fail_not_exist:
            try:
                self._perform_request(request)
                return True
            except AzureHttpError as ex:
                _dont_fail_not_exist(ex)
                return False
        else:
            self._perform_request(request)
            return True

    def get_table_acl(self, table_name, timeout=None):
        '''
        Returns details about any stored access policies specified on the
        table that may be used with Shared Access Signatures.

        :param str table_name:
            The name of an existing table.
        :param int timeout:
            The server timeout, expressed in seconds.
        :return: A dictionary of access policies associated with the table.
        :rtype: dict of str to :class:`~azure.storage.models.AccessPolicy`:
        '''
        _validate_not_none('table_name', table_name)
        request = HTTPRequest()
        request.method = 'GET'
        request.host = self._get_host()
        request.path = '/' + _str(table_name)
        request.query = [
            ('comp', 'acl'),
            ('timeout', _int_or_none(timeout)),
        ]

        response = self._perform_request(request)
        return _convert_xml_to_signed_identifiers(response.body)

    def set_table_acl(self, table_name, signed_identifiers=None, timeout=None):
        '''
        Sets stored access policies for the table that may be used with Shared 
        Access Signatures. 
        
        When you set permissions for a table, the existing permissions are replaced. 
        To update the table’s permissions, call :func:`~get_table_acl` to fetch 
        all access policies associated with the table, modify the access policy 
        that you wish to change, and then call this function with the complete 
        set of data to perform the update.

        When you establish a stored access policy on a table, it may take up to 
        30 seconds to take effect. During this interval, a shared access signature 
        that is associated with the stored access policy will throw an 
        :class:`AzureHttpError` until the access policy becomes active.

        :param str table_name:
            The name of an existing table.
        :param signed_identifiers:
            A dictionary of access policies to associate with the table. The 
            dictionary may contain up to 5 elements. An empty dictionary 
            will clear the access policies set on the service. 
        :type signed_identifiers: dict of str to :class:`~azure.storage.models.AccessPolicy`
        :param int timeout:
            The server timeout, expressed in seconds.
        '''
        _validate_not_none('table_name', table_name)
        request = HTTPRequest()
        request.method = 'PUT'
        request.host = self._get_host()
        request.path = '/' + _str(table_name)
        request.query = [
            ('comp', 'acl'),
            ('timeout', _int_or_none(timeout)),
        ]
        request.body = _get_request_body(
            _convert_signed_identifiers_to_xml(signed_identifiers))

        self._perform_request(request)

    def query_entities(self, table_name, filter=None, select=None, top=None,
                       marker=None, accept=TablePayloadFormat.JSON_MINIMAL_METADATA,
                       property_resolver=None, timeout=None):
        '''
        Returns a generator to list the entities in the table specified. The 
        generator will lazily follow the continuation tokens returned by the 
        service and stop when all entities have been returned or max_results is 
        reached.

        If max_results is specified and the account has more than that number of 
        entities, the generator will have a populated next_marker field once it 
        finishes. This marker can be used to create a new generator if more 
        results are desired.

        :param str table_name:
            The name of the table to query.
        :param str filter:
            Returns only entities that satisfy the specified filter. Note that 
            no more than 15 discrete comparisons are permitted within a $filter 
            string. See http://msdn.microsoft.com/en-us/library/windowsazure/dd894031.aspx 
            for more information on constructing filters.
        :param str select:
            Returns only the desired properties of an entity from the set.
        :param int top:
            The maximum number of entities to return.
        :param marker:
            An opaque continuation object. This value can be retrieved from the 
            next_marker field of a previous generator object if max_results was 
            specified and that generator has finished enumerating results. If 
            specified, this generator will begin returning results from the point 
            where the previous generator stopped.
        :type marker: obj
        :param str accept:
            Specifies the accepted content type of the response payload. See 
            :class:`~azure.storage.table.models.TablePayloadFormat` for possible 
            values.
        :param property_resolver:
            A function which given the partition key, row key, property name, 
            property value, and the property EdmType if returned by the service, 
            returns the EdmType of the property. Generally used if accept is set 
            to JSON_NO_METADATA.
        :type property_resolver: callback function in format of func(pk, rk, prop_name, prop_value, service_edm_type)
        :param int timeout:
            The server timeout, expressed in seconds. This function may make multiple 
            calls to the service in which case the timeout value specified will be 
            applied to each individual call.
        :return: A generator which produces :class:`~azure.storage.table.models.Entity` objects.
        :rtype: :class:`~azure.storage.models.ListGenerator`
        '''
        args = (table_name,)
        kwargs = {'filter': filter, 'select': select, 'max_results': top, 'marker': marker, 
                  'accept': accept, 'property_resolver': property_resolver, 'timeout': timeout}
        resp = self._query_entities(*args, **kwargs)

        return ListGenerator(resp, self._query_entities, args, kwargs)

    def _query_entities(self, table_name, filter=None, select=None, max_results=None,
                       marker=None, accept=TablePayloadFormat.JSON_MINIMAL_METADATA,
                       property_resolver=None, timeout=None):
        '''
        Returns a list of entities under the specified table. Makes a single list 
        request to the service. Used internally by the query_entities method.

        :param str table_name:
            The name of the table to query.
        :param str filter:
            Returns only entities that satisfy the specified filter. Note that 
            no more than 15 discrete comparisons are permitted within a $filter 
            string. See http://msdn.microsoft.com/en-us/library/windowsazure/dd894031.aspx 
            for more information on constructing filters.
        :param str select:
            Returns only the desired properties of an entity from the set.
        :param int top:
            The maximum number of entities to return.
        :param marker:
            A dictionary which identifies the portion of the query to be
            returned with the next query operation. The operation returns a
            next_marker element within the response body if the list returned
            was not complete. This value may then be used as a query parameter
            in a subsequent call to request the next portion of the list of
            queues. The marker value is opaque to the client.
        :type marker: obj
        :param str accept:
            Specifies the accepted content type of the response payload. See 
            :class:`~azure.storage.table.models.TablePayloadFormat` for possible 
            values.
        :param property_resolver:
            A function which given the partition key, row key, property name, 
            property value, and the property EdmType if returned by the service, 
            returns the EdmType of the property. Generally used if accept is set 
            to JSON_NO_METADATA.
        :type property_resolver: callback function in format of func(pk, rk, prop_name, prop_value, service_edm_type)
        :param int timeout:
            The server timeout, expressed in seconds.
        :return: A list of entities, potentially with a next_marker property.
        :rtype: list of :class:`~azure.storage.table.models.Entity`
        '''
        _validate_not_none('table_name', table_name)
        _validate_not_none('accept', accept)
        next_partition_key = None if marker is None else marker.get('nextpartitionkey')
        next_row_key = None if marker is None else marker.get('nextrowkey')

        request = HTTPRequest()
        request.method = 'GET'
        request.host = self._get_host()
        request.path = '/' + _str(table_name) + '()'
        request.headers = [('Accept', _str(accept))]
        request.query = [
            ('$filter', _str_or_none(filter)),
            ('$select', _str_or_none(select)),
            ('$top', _int_or_none(max_results)),
            ('NextPartitionKey', _str_or_none(next_partition_key)),
            ('NextRowKey', _str_or_none(next_row_key)),
            ('timeout', _int_or_none(timeout)),
        ]

        response = self._perform_request(request)
        return _convert_json_response_to_entities(response, property_resolver)

    def commit_batch(self, table_name, batch, timeout=None):
        '''
        Commits a :class:`~azure.storage.table.TableBatch` request.

        :param str table_name:
            The name of the table to commit the batch to.
        :param TableBatch batch:
            The batch to commit.
        :param int timeout:
            The server timeout, expressed in seconds.
        :return: A list of the batch responses corresponding to the requests in the batch.
        :rtype: list of response objects
        '''
        _validate_not_none('table_name', table_name)

        # Construct the batch request
        request = HTTPRequest()
        request.method = 'POST'
        request.host = self._get_host()
        request.path = '/' + '$batch'
        request.query = [('timeout', _int_or_none(timeout))]

        # Update the batch operation requests with table and client specific info
        for row_key, batch_request in batch._requests:
            batch_request.host = self._get_host()
            if batch_request.method == 'POST':
                batch_request.path = '/' + _str(table_name)
            else:
                batch_request.path = _get_entity_path(table_name, batch._partition_key, row_key)
            _update_request(batch_request)

        # Construct the batch body
        request.body, boundary = _convert_batch_to_json(batch._requests)
        request.headers = [('Content-Type', boundary)]

        # Perform the batch request and return the response
        response = self._perform_request(request)
        responses = _parse_batch_response(response.body)
        return responses

    @contextmanager
    def batch(self, table_name, timeout=None):
        '''
        Creates a batch object which can be used as a context manager. Commits the batch on exit.

        :param str table_name:
            The name of the table to commit the batch to.
        :param int timeout:
            The server timeout, expressed in seconds.
        '''
        batch = TableBatch()
        yield batch
        self.commit_batch(table_name, batch, timeout=timeout)

    def get_entity(self, table_name, partition_key, row_key, select=None,
                   accept=TablePayloadFormat.JSON_MINIMAL_METADATA,
                   property_resolver=None, timeout=None):
        '''
        Get an entity from the specified table. Throws if the entity does not exist.

        :param str table_name:
            The name of the table to get the entity from.
        :param str partition_key:
            The PartitionKey of the entity.
        :param str row_key:
            The RowKey of the entity.
        :param str select:
            Returns only the desired properties of an entity from the set.
        :param str accept:
            Specifies the accepted content type of the response payload. See 
            :class:`~azure.storage.table.models.TablePayloadFormat` for possible 
            values.
        :param property_resolver:
            A function which given the partition key, row key, property name, 
            property value, and the property EdmType if returned by the service, 
            returns the EdmType of the property. Generally used if accept is set 
            to JSON_NO_METADATA.
        :type property_resolver: callback function in format of func(pk, rk, prop_name, prop_value, service_edm_type)
        :param int timeout:
            The server timeout, expressed in seconds.
        :return: The retrieved entity.
        :rtype: :class:`~azure.storage.table.models.Entity`
        '''
        _validate_not_none('table_name', table_name)
        request = _get_entity(partition_key, row_key, select, accept)
        request.host = self._get_host()
        request.path = _get_entity_path(table_name, partition_key, row_key)
        request.query += [('timeout', _int_or_none(timeout))]

        response = self._perform_request(request)
        return _convert_json_response_to_entity(response, property_resolver)

    def insert_entity(self, table_name, entity, timeout=None):
        '''
        Inserts a new entity into the table. Throws if an entity with the same 
        PartitionKey and RowKey already exists.

        When inserting an entity into a table, you must specify values for the 
        PartitionKey and RowKey system properties. Together, these properties 
        form the primary key and must be unique within the table. Both the 
        PartitionKey and RowKey values must be string values; each key value may 
        be up to 64 KB in size. If you are using an integer value for the key 
        value, you should convert the integer to a fixed-width string, because 
        they are canonically sorted. For example, you should convert the value 
        1 to 0000001 to ensure proper sorting.

        :param str table_name:
            The name of the table to insert the entity into.
        :param entity:
            The entity to insert. Could be a dict or an entity object. 
            Must contain a PartitionKey and a RowKey.
        :type entity: a dict or :class:`~azure.storage.table.models.Entity`
        :param int timeout:
            The server timeout, expressed in seconds.
        :return: The etag of the inserted entity.
        :rtype: str
        '''
        _validate_not_none('table_name', table_name)
        request = _insert_entity(entity)
        request.host = self._get_host()
        request.path = '/' + _str(table_name)
        request.query += [('timeout', _int_or_none(timeout))]

        response = self._perform_request(request)
        return _extract_etag(response)

    def update_entity(self, table_name, entity, if_match='*', timeout=None):
        '''
        Updates an existing entity in a table. Throws if the entity does not exist. 
        The update_entity operation replaces the entire entity and can be used to 
        remove properties.

        :param str table_name:
            The name of the table containing the entity to update.
        :param entity:
            The entity to update. Could be a dict or an entity object. 
            Must contain a PartitionKey and a RowKey.
        :type entity: a dict or :class:`~azure.storage.table.models.Entity`
        :param str if_match:
            The client may specify the ETag for the entity on the 
            request in order to compare to the ETag maintained by the service 
            for the purpose of optimistic concurrency. The update operation 
            will be performed only if the ETag sent by the client matches the 
            value maintained by the server, indicating that the entity has 
            not been modified since it was retrieved by the client. To force 
            an unconditional update, set If-Match to the wildcard character (*).
        :param int timeout:
            The server timeout, expressed in seconds.
        :return: The etag of the entity.
        :rtype: str
        '''
        _validate_not_none('table_name', table_name)
        request = _update_entity(entity, if_match)
        request.host = self._get_host()
        request.path = _get_entity_path(table_name, entity['PartitionKey'], entity['RowKey'])
        request.query += [('timeout', _int_or_none(timeout))]

        response = self._perform_request(request)
        return _extract_etag(response)

    def merge_entity(self, table_name, entity, if_match='*', timeout=None):
        '''
        Updates an existing entity by merging the entity's properties. Throws 
        if the entity does not exist. 
        
        This operation does not replace the existing entity as the update_entity
        operation does. A property cannot be removed with merge_entity.
        
        Any properties with null values are ignored. All other properties will be 
        updated or added.

        :param str table_name:
            The name of the table containing the entity to merge.
        :param entity:
            The entity to merge. Could be a dict or an entity object. 
            Must contain a PartitionKey and a RowKey.
        :type entity: a dict or :class:`~azure.storage.table.models.Entity`
        :param str if_match:
            The client may specify the ETag for the entity on the 
            request in order to compare to the ETag maintained by the service 
            for the purpose of optimistic concurrency. The merge operation 
            will be performed only if the ETag sent by the client matches the 
            value maintained by the server, indicating that the entity has 
            not been modified since it was retrieved by the client. To force 
            an unconditional merge, set If-Match to the wildcard character (*).
        :param int timeout:
            The server timeout, expressed in seconds.
        :return: The etag of the entity.
        :rtype: str
        '''
        _validate_not_none('table_name', table_name)
        request = _merge_entity(entity, if_match)
        request.host = self._get_host()
        request.query += [('timeout', _int_or_none(timeout))]
        request.path = _get_entity_path(table_name, entity['PartitionKey'], entity['RowKey'])

        response = self._perform_request(request)
        return _extract_etag(response)

    def delete_entity(self, table_name, partition_key, row_key,
                      if_match='*', timeout=None):
        '''
        Deletes an existing entity in a table. Throws if the entity does not exist.

        When an entity is successfully deleted, the entity is immediately marked 
        for deletion and is no longer accessible to clients. The entity is later 
        removed from the Table service during garbage collection.

        :param str table_name:
            The name of the table containing the entity to delete.
        :param str partition_key:
            The PartitionKey of the entity.
        :param str row_key:
            The RowKey of the entity.
        :param str if_match:
            The client may specify the ETag for the entity on the 
            request in order to compare to the ETag maintained by the service 
            for the purpose of optimistic concurrency. The delete operation 
            will be performed only if the ETag sent by the client matches the 
            value maintained by the server, indicating that the entity has 
            not been modified since it was retrieved by the client. To force 
            an unconditional delete, set If-Match to the wildcard character (*).
        :param int timeout:
            The server timeout, expressed in seconds.
        '''
        _validate_not_none('table_name', table_name)
        request = _delete_entity(partition_key, row_key, if_match)
        request.host = self._get_host()
        request.query += [('timeout', _int_or_none(timeout))]
        request.path = _get_entity_path(table_name, partition_key, row_key)

        self._perform_request(request)

    def insert_or_replace_entity(self, table_name, entity, timeout=None):
        '''
        Replaces an existing entity or inserts a new entity if it does not
        exist in the table. Because this operation can insert or update an
        entity, it is also known as an "upsert" operation.

        If insert_or_replace_entity is used to replace an entity, any properties 
        from the previous entity will be removed if the new entity does not define 
        them.

        :param str table_name:
            The name of the table in which to insert or replace the entity.
        :param entity:
            The entity to insert or replace. Could be a dict or an entity object. 
            Must contain a PartitionKey and a RowKey.
        :type entity: a dict or :class:`~azure.storage.table.models.Entity`
        :param int timeout:
            The server timeout, expressed in seconds.
        :return: The etag of the entity.
        :rtype: str
        '''
        _validate_not_none('table_name', table_name)
        request = _insert_or_replace_entity(entity)
        request.host = self._get_host()
        request.query += [('timeout', _int_or_none(timeout))]
        request.path = _get_entity_path(table_name, entity['PartitionKey'], entity['RowKey'])

        response = self._perform_request(request)
        return _extract_etag(response)

    def insert_or_merge_entity(self, table_name, entity, timeout=None):
        '''
        Merges an existing entity or inserts a new entity if it does not exist
        in the table. 

        If insert_or_merge_entity is used to merge an entity, any properties from 
        the previous entity will be retained if the request does not define or 
        include them.

        :param str table_name:
            The name of the table in which to insert or merge the entity.
        :param entity:
            The entity to insert or merge. Could be a dict or an entity object. 
            Must contain a PartitionKey and a RowKey.
        :type entity: a dict or :class:`~azure.storage.table.models.Entity`
        :param int timeout:
            The server timeout, expressed in seconds.
        :return: The etag of the entity.
        :rtype: str
        '''
        _validate_not_none('table_name', table_name)
        request = _insert_or_merge_entity(entity)
        request.host = self._get_host()
        request.query += [('timeout', _int_or_none(timeout))]
        request.path = _get_entity_path(table_name, entity['PartitionKey'], entity['RowKey'])

        response = self._perform_request(request)
        return _extract_etag(response)

    def _perform_request_worker(self, request):
        _update_storage_table_header(request)
        return super(TableService, self)._perform_request_worker(request)