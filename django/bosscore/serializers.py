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

from rest_framework import serializers
from django.contrib.auth.models import User, Group
from guardian.shortcuts import get_objects_for_user
from .models import Collection, Experiment, ChannelLayer, CoordinateFrame, ChannelLayerMap, BossLookup, BossRole


class UserSerializer(serializers.ModelSerializer):
    collections = serializers.PrimaryKeyRelatedField(many=True, queryset=Collection.objects.all())

    class Meta:
        model = User
        fields = ('id', 'username', 'collections')


class CoordinateFrameSerializer(serializers.ModelSerializer):

    class Meta:
        model = CoordinateFrame
        fields = ('id', 'name', 'description', 'x_start', 'x_stop', 'y_start', 'y_stop', 'z_start', 'z_stop',
                  'x_voxel_size', 'y_voxel_size', 'z_voxel_size', 'voxel_unit', 'time_step', 'time_step_unit')

class CoordinateFrameUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = CoordinateFrame
        fields = ('name', 'description')

    def is_valid(self, raise_exception=False):
        super().is_valid(False)

        fields_keys = set(self.fields.keys())
        input_keys = set(self.initial_data.keys())

        additional_fields = input_keys - fields_keys

        if bool(additional_fields):
            self._errors['fields'] = ['Cannot update the following readonly fields: {}.'.format(list(additional_fields))]

        if self._errors and raise_exception:
            raise serializers.ValidationError(self.errors)

        return not bool(self._errors)

class ChannelLayerMapSerializer(serializers.ModelSerializer):

    class Meta:
        model = ChannelLayerMap
        fields = ('channel', 'layer')


class NameOnlySerializer(serializers.ModelSerializer):

    class Meta:
        model = ChannelLayer
        fields = ('name',)


class ChannelSerializer(serializers.ModelSerializer):
    linked_channel_layers = NameOnlySerializer(many=True, read_only=True)
    is_channel = serializers.BooleanField(default=True, read_only=True)
    creator = serializers.ReadOnlyField(source='creator.username')

    class Meta:
        model = ChannelLayer
        fields = ('id', 'name', 'description', 'experiment', 'is_channel', 'default_time_step',
                  'base_resolution', 'datatype', 'linked_channel_layers', 'creator')


class LayerSerializer(serializers.ModelSerializer):
    linked_channel_layers = NameOnlySerializer(many=True, read_only=True)
    is_channel = serializers.BooleanField(default=False, read_only=True)
    creator = serializers.ReadOnlyField(source='creator.username')

    class Meta:
        model = ChannelLayer
        fields = ('id', 'name', 'description', 'is_channel', 'experiment', 'default_time_step',
                  'base_resolution', 'datatype', 'linked_channel_layers', 'creator')


class ChannelLayerSerializer(serializers.ModelSerializer):
    creator = serializers.ReadOnlyField(source='creator.username')

    class Meta:
        model = ChannelLayer
        fields = ('id', 'name', 'description', 'experiment', 'is_channel', 'default_time_step', 'datatype',
                  'base_resolution', 'linked_channel_layers', 'creator')


class ExperimentSerializer(serializers.ModelSerializer):
    channel_layers = ChannelLayerSerializer(many=True, read_only=True)
    creator = serializers.ReadOnlyField(source='creator.username')

    def get_fields(self):
        fields = super(ExperimentSerializer, self).get_fields()
        if 'request' in self.context:
            collections = get_objects_for_user(self.context['view'].request.user, 'add_collection', klass=Collection)
            fields['collection'].queryset = collections
        return fields

    class Meta:
        model = Experiment
        fields = ('id', 'name', 'description', 'collection', 'coord_frame', 'num_hierarchy_levels', 'hierarchy_method',
                  'max_time_sample', 'channel_layers', 'creator')


class CollectionSerializer(serializers.ModelSerializer):
    experiments = ExperimentSerializer(many=True, read_only=True)
    creator = serializers.ReadOnlyField(source='creator.username')

    class Meta:
        model = Collection
        fields = ('id', 'name', 'description', 'experiments', 'creator')
        depth = 1


class BossLookupSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='pk')

    class Meta:
        model = BossLookup
        fields = ('id', 'lookup_key', 'boss_key', 'collection_name', 'experiment_name', 'channel_layer_name')


class BossRoleSerializer(serializers.ModelSerializer):

    class Meta:
        model = BossRole
        fields = ('user', 'role')


class GroupSerializer(serializers.ModelSerializer):

    class Meta:
        model = Group
        fields = ('id','name')


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ('id','username', 'first_name', 'last_name', 'email')
