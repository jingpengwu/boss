# Copyright 2016 The Johns Hopkins University Applied Physics Laboratory
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from guardian.shortcuts import get_objects_for_user
from functools import wraps

from bosscore.error import BossHTTPError, BossPermissionError, BossResourceNotFoundError, ErrorCodes
from bosscore.lookup import LookUpKey
from bosscore.permissions import BossPermissionManager
from bosscore.privileges import check_role

from bosscore.serializers import CollectionSerializer, ExperimentSerializer, ChannelLayerSerializer,\
    LayerSerializer, CoordinateFrameSerializer, CoordinateFrameUpdateSerializer, ChannelLayerMapSerializer
from bosscore.models import Collection, Experiment, ChannelLayer, CoordinateFrame


class CollectionDetail(APIView):

    """
    View to access a collection object

    """
    def get(self, request, collection):
        """
        Get a single instance of a collection

        Args:
            request: DRF Request object
            collection: Collection name specifying the collection you want
        Returns:
            Collection
        """
        try:
            collection_obj = Collection.objects.get(name=collection)

            # Check for permissions
            if request.user.has_perm("read", collection_obj):
                serializer = CollectionSerializer(collection_obj)
                return Response(serializer.data, status=200)
            else:
                return BossPermissionError('read', collection)
        except Collection.DoesNotExist:
            return BossResourceNotFoundError(collection)

    @transaction.atomic
    @check_role("resource-manager")
    def post(self, request, collection):
        """Create a new collection

        View to create a new collection and an associated bosskey for that collection
        Args:
            request: DRF Request object
            collection : Collection name
        Returns:
            Collection

        """
        col_data = request.data.copy()
        col_data['name'] = collection

        serializer = CollectionSerializer(data=col_data)
        if serializer.is_valid():
            serializer.save(creator=self.request.user)
            collection_obj = Collection.objects.get(name=col_data['name'])

            # Assign permissions to the users primary group
            BossPermissionManager.add_permissions_primary_group(self.request.user, collection_obj)
            BossPermissionManager.add_permissions_admin_group(collection_obj)

            lookup_key = str(collection_obj.pk)
            boss_key = collection_obj.name
            LookUpKey.add_lookup(lookup_key, boss_key, collection_obj.name)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return BossHTTPError("{}".format(serializer.errors), ErrorCodes.INVALID_POST_ARGUMENT)

    @transaction.atomic
    def put(self, request, collection):
        """
        Update a collection using django rest framework
        Args:
            request: DRF Request object
            collection: Collection name
        Returns:
            Collection
        """
        try:
            # Check if the object exists
            collection_obj = Collection.objects.get(name=collection)

            # Check for permissions
            if request.user.has_perm("update", collection_obj):
                serializer = CollectionSerializer(collection_obj, data=request.data, partial=True)
                if serializer.is_valid():
                    serializer.save()

                    # update the lookup key if you update the name
                    if 'name' in request.data and request.data['name'] != collection:
                        lookup_key = str(collection_obj.pk)
                        boss_key = request.data['name']
                        LookUpKey.update_lookup(lookup_key, boss_key, request.data['name'])

                    return Response(serializer.data)
                else:
                    return BossHTTPError("{}".format(serializer.errors), ErrorCodes.INVALID_POST_ARGUMENT)
            else:
                return BossPermissionError('update', collection)
        except Collection.DoesNotExist:
            return BossResourceNotFoundError(collection)

    @transaction.atomic
    @check_role("resource-manager")
    def delete(self, request, collection):
        """
        Delete a collection
        Args:
            request: DRF Request object
            collection:  Name of collection to delete
        Returns:
            Http status
        """
        try:
            collection_obj = Collection.objects.get(name=collection)
            if request.user.has_perm("delete", collection_obj):
                collection_obj.delete()
                # # get the lookup key and delete all the meta data for this object
                # lkey = LookUpKey.get_lookup_key(collection)
                # mdb = MetaDB()
                # mdb.delete_meta_keys(lkey.lookup_key)

                # delete the lookup key for this object
                LookUpKey.delete_lookup_key(collection, None, None)

                return HttpResponse(status=204)
            else:
                return BossPermissionError('delete', collection)
        except Collection.DoesNotExist:
            return BossResourceNotFoundError(collection)
        except ProtectedError:
            return BossHTTPError("Cannot delete {}. It has experiments that reference it.".format(collection),
                                 ErrorCodes.INTEGRITY_ERROR)


class CoordinateFrameDetail(APIView):
    """
    View to access a cordinate frame

    """
    def get(self, request, coordframe):
        """
        GET requests for a single instance of a coordinateframe
        Args:

            request: DRF Request object
            coordframe: Coordinate frame name specifying the coordinate frame you want
        Returns:
            CoordinateFrame
        """
        try:
            coordframe_obj = CoordinateFrame.objects.get(name=coordframe)
            serializer = CoordinateFrameSerializer(coordframe_obj)
            return Response(serializer.data)
        except CoordinateFrame.DoesNotExist:
            return BossResourceNotFoundError(coordframe)

    @transaction.atomic
    @check_role("resource-manager")
    def post(self, request, coordframe):
        """Create a new coordinate frame

        View to create a new coordinate frame
        Args:
            request: DRF Request object
            coordframe : Coordinate frame name
        Returns:
            CoordinateFrame

        """
        coordframe_data = request.data.copy()
        coordframe_data['name'] = coordframe

        serializer = CoordinateFrameSerializer(data=coordframe_data)
        if serializer.is_valid():
            serializer.save(creator=self.request.user)
            coordframe_obj = CoordinateFrame.objects.get(name=coordframe_data['name'])

            # Assign permissions to the users primary group
            BossPermissionManager.add_permissions_primary_group(self.request.user, coordframe_obj)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return BossHTTPError("{}".format(serializer.errors), ErrorCodes.INVALID_POST_ARGUMENT)

    @transaction.atomic
    def put(self, request, coordframe):
        """
        Update a coordinate frame using django rest framework

        Args:
            request: DRF Request object
            coordframe: Coordinate frame name
        Returns:
            CoordinateFrame
        """
        try:
            # Check if the object exists
            coordframe_obj = CoordinateFrame.objects.get(name=coordframe)

            if request.user.has_perm("update", coordframe_obj):
                serializer = CoordinateFrameUpdateSerializer(coordframe_obj, data=request.data, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    return Response(serializer.data)
                else:
                    return BossHTTPError("{}".format(serializer.errors), ErrorCodes.INVALID_POST_ARGUMENT)
            else:
                return BossPermissionError('update', coordframe)
        except CoordinateFrame.DoesNotExist:
            return BossResourceNotFoundError(coordframe)

    @transaction.atomic
    @check_role("resource-manager")
    def delete(self, request, coordframe):
        """
        Delete a coordinate frame
        Args:
            request: DRF Request object
            coordframe:  Name of coordinateframe to delete
        Returns:
            Http status
        """
        try:
            coordframe_obj = CoordinateFrame.objects.get(name=coordframe)
            if request.user.has_perm("delete", coordframe_obj):
                coordframe_obj.delete()
                return HttpResponse(status=204)
            else:
                return BossPermissionError('delete', coordframe)
        except CoordinateFrame.DoesNotExist:
            return BossResourceNotFoundError(coordframe)
        except ProtectedError:
            return BossHTTPError("Cannot delete {}. It has experiments that reference it.".format(coordframe),
                                 ErrorCodes.INTEGRITY_ERROR)


class ExperimentDetail(APIView):
    """
    View to access an experiment

    """
    def get(self, request, collection, experiment):
        """
        GET requests for a single instance of a experiment

        Args:
            request: DRF Request object
            collection: Collection name specifying the collection you want
            experiment: Experiment name specifying the experiment instance
        Returns :
            Experiment
        """
        try:
            collection_obj = Collection.objects.get(name=collection)
            experiment_obj = Experiment.objects.get(name=experiment, collection=collection_obj)
            # Check for permissions
            if request.user.has_perm("read", experiment_obj):
                serializer = ExperimentSerializer(experiment_obj)
                return Response(serializer.data)
            else:
                return BossPermissionError('read', experiment)
        except Collection.DoesNotExist:
            return BossResourceNotFoundError(collection)
        except Experiment.DoesNotExist:
            return BossResourceNotFoundError(experiment)

    @transaction.atomic
    @check_role("resource-manager")
    def post(self, request, collection, experiment):
        """Create a new experiment

        View to create a new experiment and an associated bosskey for that experiment
        Args:
            request: DRF Request object
            collection : Collection name
            experiment : Experiment name
        Returns:
            Experiment

        """
        experiment_data = request.data.copy()
        experiment_data['name'] = experiment
        try:
            # Get the collection information
            collection_obj = Collection.objects.get(name=collection)

            if request.user.has_perm("add", collection_obj):
                experiment_data['collection'] = collection_obj.pk

                serializer = ExperimentSerializer(data=experiment_data)
                if serializer.is_valid():
                    serializer.save(creator=self.request.user)
                    experiment_obj = Experiment.objects.get(name=experiment_data['name'])

                    # Assign permissions to the users primary group
                    BossPermissionManager.add_permissions_primary_group(self.request.user, experiment_obj)

                    lookup_key = str(collection_obj.pk) + '&' + str(experiment_obj.pk)
                    boss_key = collection_obj.name + '&' + experiment_obj.name
                    LookUpKey.add_lookup(lookup_key, boss_key, collection_obj.name, experiment_obj.name)

                    return Response(serializer.data, status=status.HTTP_201_CREATED)
                else:
                    return BossHTTPError("{}".format(serializer.errors), ErrorCodes.INVALID_POST_ARGUMENT)
            else:
                return BossPermissionError('add', collection)
        except Collection.DoesNotExist:
            return BossResourceNotFoundError(collection)
        except ValueError:
            return BossHTTPError("Value Error.Collection id {} in post data needs to "
                                      "be an integer".format(experiment_data['collection']), ErrorCodes.TYPE_ERROR)

    @transaction.atomic
    def put(self, request, collection, experiment):
        """
        Update a experiment using django rest framework

        Args:
            request: DRF Request object
            collection: Collection name
            experiment : Experiment name for the new experiment

        Returns:
            Experiment
        """
        try:
            # Check if the object exists
            collection_obj = Collection.objects.get(name=collection)
            experiment_obj = Experiment.objects.get(name=experiment, collection=collection_obj)
            if request.user.has_perm("update", experiment_obj):
                serializer = ExperimentSerializer(experiment_obj, data=request.data, partial=True)
                if serializer.is_valid():
                    serializer.save()

                    # update the lookup key if you update the name
                    if 'name' in request.data and request.data['name'] != experiment:
                        lookup_key = str(collection_obj.pk) + '&' + str(experiment_obj.pk)
                        boss_key = collection_obj.name + '&' + request.data['name']
                        LookUpKey.update_lookup(lookup_key, boss_key, collection_obj.name, request.data['name'])

                    return Response(serializer.data)
                else:
                    return BossHTTPError("{}".format(serializer.errors), ErrorCodes.INVALID_POST_ARGUMENT)
            else:
                return BossPermissionError('update', experiment)

        except Collection.DoesNotExist:
            return BossResourceNotFoundError(collection)
        except Experiment.DoesNotExist:
            return BossResourceNotFoundError(experiment)

    @transaction.atomic
    @check_role("resource-manager")
    def delete(self, request, collection, experiment):
        """
        Delete a experiment
        Args:
            request: DRF Request object
            collection:  Name of collection
            experiment: Experiment name to delete
        Returns:
            Http status
        """
        try:
            collection_obj = Collection.objects.get(name=collection)
            experiment_obj = Experiment.objects.get(name=experiment, collection=collection_obj)
            if request.user.has_perm("delete", experiment_obj):
                experiment_obj.delete()
                # # get the lookup key and delete all the meta data for this object
                # bosskey = collection + '&' + experiment
                # lkey = LookUpKey.get_lookup_key(bosskey)
                # mdb = MetaDB()
                # mdb.delete_meta_keys(lkey)

                # delete the lookup key for this object
                LookUpKey.delete_lookup_key(collection, experiment, None)
                return HttpResponse(status=204)
            else:
                return BossPermissionError('delete', experiment)
        except Collection.DoesNotExist:
            return BossResourceNotFoundError(collection)
        except Experiment.DoesNotExist:
            return BossResourceNotFoundError(experiment)
        except ProtectedError:
            return BossHTTPError("Cannot delete {}. It has channels or layers that reference "
                                      "it.".format(experiment), ErrorCodes.INTEGRITY_ERROR)


class ChannelLayerDetail(APIView):
    """
    View to access a channel

    """
    @staticmethod
    def get_bool(value):
        """
        Convert a string to a bool

        Boolean variables in post data get converted to strings. This method converts the variables
        back to a boolean if they are valid.

        Args:
            value:

        Returns:
            Boolean : True if the string is "True"

        Raises:
            BossError : If the value of the string is not a valid bool

        """
        if value == "true" or value == "True":
            return True
        elif value == "false" or value == "False":
            return False
        else:
            return BossHTTPError("Value Error in post data", ErrorCodes.TYPE_ERROR)

    def get(self, request, collection, experiment, channel_layer):
        """
        Retrieve information about a channel.
        Args:
            request: DRF Request object
            collection: Collection name
            experiment: Experiment name
            channel_layer: Channel or Layer name

        Returns :
            ChannelLayer
        """
        try:
            collection_obj = Collection.objects.get(name=collection)
            experiment_obj = Experiment.objects.get(name=experiment, collection=collection_obj)
            channel_layer_obj = ChannelLayer.objects.get(name=channel_layer, experiment=experiment_obj)

            # Check for permissions
            if request.user.has_perm("read", channel_layer_obj):
                serializer = ChannelLayerSerializer(channel_layer_obj)
                return Response(serializer.data)
            else:
                return BossPermissionError('read', channel_layer)

        except Collection.DoesNotExist:
            return BossResourceNotFoundError(collection)
        except Experiment.DoesNotExist:
            return BossResourceNotFoundError(experiment)
        except ChannelLayer.DoesNotExist:
            return BossResourceNotFoundError(channel_layer)
        except ValueError:
            return BossHTTPError("Value Error in post data", ErrorCodes.TYPE_ERROR)

    @transaction.atomic
    @check_role("resource-manager")
    def post(self, request, collection, experiment, channel_layer):
        """
        Post a new Channel
        Args:
            request: DRF Request object
            collection: Collection name
            experiment: Experiment name
            channel_layer: Channel or Layer name

        Returns :
            ChannelLayer
        """

        channel_layer_data = request.data.copy()
        channel_layer_data['name'] = channel_layer

        try:
            if 'channels' in channel_layer_data:
                channels = dict(channel_layer_data)['channels']
            else:
                channels = []
            collection_obj = Collection.objects.get(name=collection)
            experiment_obj = Experiment.objects.get(name=experiment, collection=collection_obj)
            # Check for add permissions
            if request.user.has_perm("add", experiment_obj):
                channel_layer_data['experiment'] = experiment_obj.pk
                channel_layer_data['is_channel'] = self.get_bool(channel_layer_data['is_channel'])

                # layers require at least 1 channel
                if (channel_layer_data['is_channel'] is False) and (len(channels) == 0):
                    return BossHTTPError("Invalid Request.Please specify a valid channel for the layer",
                                         ErrorCodes.INVALID_POST_ARGUMENT)

                serializer = ChannelLayerSerializer(data=channel_layer_data)
                if serializer.is_valid():
                    serializer.save(creator=self.request.user)
                    channel_layer_obj = ChannelLayer.objects.get(name=channel_layer_data['name'],
                                                                 experiment=experiment_obj)

                    # Layer?
                    if not channel_layer_obj.is_channel:
                        # Layers must map to at least 1 channel
                        for channel_id in channels:
                            # Is this a valid channel?
                            channel_obj = ChannelLayer.objects.get(pk=channel_id)
                            if channel_obj:
                                channel_layer_map = {'channel': channel_id, 'layer': channel_layer_obj.pk}
                                map_serializer = ChannelLayerMapSerializer(data=channel_layer_map)
                                if map_serializer.is_valid():
                                    map_serializer.save()

                    # Assign permissions to the users primary group
                    BossPermissionManager.add_permissions_primary_group(self.request.user, channel_layer_obj)

                    # Add Lookup key
                    lookup_key = str(collection_obj.pk) + '&' + str(experiment_obj.pk) + '&' + str(channel_layer_obj.pk)
                    boss_key = collection_obj.name + '&' + experiment_obj.name + '&' + channel_layer_obj.name
                    LookUpKey.add_lookup(lookup_key, boss_key, collection_obj.name, experiment_obj.name,
                                         channel_layer_obj.name)

                    return Response(serializer.data, status=status.HTTP_201_CREATED)
                else:
                    return BossHTTPError("{}".format(serializer.errors), ErrorCodes.INVALID_POST_ARGUMENT)
            else:
                return BossPermissionError('add', experiment)
        except Collection.DoesNotExist:
            return BossResourceNotFoundError(collection)
        except Experiment.DoesNotExist:
            return BossResourceNotFoundError(experiment)
        except ChannelLayer.DoesNotExist:
            return BossResourceNotFoundError(channel_layer)
        except ValueError:
            return BossHTTPError("Value Error in post data", ErrorCodes.TYPE_ERROR)

    @transaction.atomic
    def put(self, request, collection, experiment, channel_layer):
        """
        Update new Channel or Layer
        Args:
            request: DRF Request object
            collection: Collection name
            experiment: Experiment name
            channel_layer: Channel or Layer name

        Returns :
            ChannelLayer
        """
        channel_layer_data = request.data.copy()
        if 'is_channel' in channel_layer_data:
            channel_layer_data['is_channel'] = self.get_bool(channel_layer_data['is_channel'])

        try:
            # Check if the object exists
            collection_obj = Collection.objects.get(name=collection)
            experiment_obj = Experiment.objects.get(name=experiment, collection=collection_obj)
            channel_layer_obj = ChannelLayer.objects.get(name=channel_layer, experiment=experiment_obj)
            if request.user.has_perm("update", channel_layer_obj):
                serializer = ChannelLayerSerializer(channel_layer_obj, data=request.data, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    # update the lookup key if you update the name
                    if 'name' in request.data and request.data['name'] != channel_layer:
                        lookup_key = str(collection_obj.pk) + '&' + str(experiment_obj.pk) + '&' \
                                     + str(channel_layer_obj.pk)
                        boss_key = collection_obj.name + '&' + experiment_obj.name + '&' + request.data['name']
                        LookUpKey.update_lookup(lookup_key, boss_key, collection_obj.name,  experiment_obj.name,
                                                request.data['name'])

                    return Response(serializer.data)
                else:
                    return BossHTTPError("{}".format(serializer.errors), ErrorCodes.INVALID_POST_ARGUMENT)
            else:
                return BossPermissionError('update', channel_layer)

        except Collection.DoesNotExist:
            return BossResourceNotFoundError(collection)
        except Experiment.DoesNotExist:
            return BossResourceNotFoundError(experiment)
        except ChannelLayer.DoesNotExist:
            return BossResourceNotFoundError(channel_layer)

    @transaction.atomic
    @check_role("resource-manager")
    def delete(self, request, collection, experiment, channel_layer):
        """
        Delete a Channel  or a Layer
        Args:
            request: DRF Request object
            collection: Collection name
            experiment: Experiment name
            channel_layer: Channel or Layer name

        Returns :
            Http status
        """
        try:
            collection_obj = Collection.objects.get(name=collection)
            experiment_obj = Experiment.objects.get(name=experiment, collection=collection_obj)
            channel_layer_obj = ChannelLayer.objects.get(name=channel_layer, experiment=experiment_obj)

            if request.user.has_perm("delete", channel_layer_obj):
                channel_layer_obj.delete()

                # delete the lookup key for this object
                LookUpKey.delete_lookup_key(collection, experiment, channel_layer)
                return HttpResponse(status=204)
            else:
                return BossPermissionError('delete', channel_layer)

        except Collection.DoesNotExist:
            return BossResourceNotFoundError(collection)
        except Experiment.DoesNotExist:
            return BossResourceNotFoundError(experiment)
        except ChannelLayer.DoesNotExist:
            return BossResourceNotFoundError(channel_layer)
        except ProtectedError:
            return BossHTTPError("Cannot delete {}. It has layers that reference it.".format(channel_layer),
                                 ErrorCodes.INTEGRITY_ERROR)


class CollectionList(generics.ListAPIView):
    """
    List all collections or create a new collection

    """
    queryset = Collection.objects.all()
    serializer_class = CollectionSerializer

    def list(self, request, *args, **kwargs):
        """
        Display only objects that a user has access to
        Args:
            request: DRF request
            *args:
            **kwargs:

        Returns: Collections that user has view permissions on

        """
        # queryset = self.get_queryset()
        collections = get_objects_for_user(request.user, 'read', klass=Collection)
        serializer = CollectionSerializer(collections, many=True)
        return Response(serializer.data)


class ExperimentList(generics.ListAPIView):
    """
    List all experiments
    """

    queryset = Experiment.objects.all()
    serializer_class = ExperimentSerializer

    def list(self, request, collection, *args, **kwargs):
        """
        return experiments for the collection that the user has permissions for
        Args:
            request: DRF request
            collection : Collection name
            *args:
            **kwargs:

        Returns: Experiments that user has view permissions on

        """
        collection_obj = Collection.objects.get(name=collection)
        all_experiments = get_objects_for_user(request.user, 'read', klass=Experiment)
        experiments = all_experiments.filter(collection=collection_obj)
        serializer = ExperimentSerializer(experiments, many=True)
        return Response(serializer.data)


class ChannelList(generics.ListAPIView):
    """
    List all channels
    """
    queryset = ChannelLayer.objects.all()
    serializer_class = ChannelLayerSerializer

    def list(self, request, collection, experiment, *args, **kwargs):
        """
        Display only objects that a user has access to
        Args:
            request: DRF request
            collection: Collection Name
            experiment: Experiment Name

            *args:
            **kwargs:

        Returns: Channel_Layers that user has view permissions on

        """
        collection_obj = Collection.objects.get(name=collection)
        experiment_obj = Experiment.objects.get(name=experiment, collection=collection_obj)
        channel_layers = get_objects_for_user(request.user, 'read',
                                              klass=ChannelLayer).filter(is_channel=True, experiment=experiment_obj)
        serializer = ChannelLayerSerializer(channel_layers, many=True)
        return Response(serializer.data)


class LayerList(generics.ListAPIView):
    """
    List all layers
    """
    queryset = ChannelLayer.objects.filter(is_channel=False)
    serializer_class = LayerSerializer

    def list(self, request, collection, experiment, *args, **kwargs):
        """
        Display only objects that a user has access to
        Args:
            request: DRF request
            *args:
            **kwargs:

        Returns: Channel_Layers that user has view permissions on

        """
        collection_obj = Collection.objects.get(name=collection)
        experiment_obj = Experiment.objects.get(name=experiment, collection=collection_obj)
        channel_layers = get_objects_for_user(request.user, 'read',
                                              klass=ChannelLayer).filter(is_channel=False, experiment=experiment_obj)
        serializer = ChannelLayerSerializer(channel_layers, many=True)
        return Response(serializer.data)


class CoordinateFrameList(generics.ListCreateAPIView):
    """
    List all coordinate frames
    """
    queryset = CoordinateFrame.objects.all()
    serializer_class = CoordinateFrameSerializer

    def list(self, request, *args, **kwargs):
        """
        Display only objects that a user has access to
        Args:
            request: DRF request
            *args:
            **kwargs:

        Returns: Coordinate frames that user has view permissions on

        """
        coords = get_objects_for_user(request.user, 'read', klass=CoordinateFrame)
        serializer = CoordinateFrameSerializer(coords, many=True)
        return Response(serializer.data)
