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

import json
import os

from ingest.core.config import Configuration
from ingest.core.backend import BossBackend

from bossingest.serializers import IngestJobCreateSerializer, IngestJobListSerializer
from bossingest.models import IngestJob

from bosscore.error import BossError, ErrorCodes, BossResourceNotFoundError
from bosscore.models import Collection, Experiment, ChannelLayer
from bosscore.lookup import LookUpKey

from ndingest.ndqueue.uploadqueue import UploadQueue
from ndingest.ndqueue.ingestqueue import IngestQueue
from ndingest.ndingestproj.bossingestproj import BossIngestProj
from ndingest.ndbucket.tilebucket import TileBucket
from ndingest.nddynamo.boss_tileindexdb import BossTileIndexDB
from ndingest.ndbucket.tilebucket import TileBucket

from bossutils.ingestcreds import IngestCredentials
from ndingest.util.bossutil import BossUtil
import jsonschema

CONNECTER = '&'


class IngestManager:
    """
    Helper function for the boss ingest service

    """

    def __init__(self):
        """
         Init function
        """
        self.job = None
        self.owner = None
        self.config = None
        self.validator = None
        self.collection = None
        self.experiment = None
        self.channel_layer = None
        self.resolution = 0
        self.nd_proj = None

    def validate_config_file(self, config_data):
        """
        Method to validate an ingest config file
        Args:
            config_data:

        Returns:

        """

        try:
            # Validate the schema
            self.config = Configuration(config_data)
            self.validator = self.config.get_validator()
            self.validator.schema = self.config.schema
            self.validator.validate_schema()
        except jsonschema.ValidationError as e:
            raise BossError("Schema validation failed! {}".format(e), ErrorCodes.UNABLE_TO_VALIDATE)
        except Exception as e:
            raise BossError(" Could not validate the schema file.{}".format(e), ErrorCodes.UNABLE_TO_VALIDATE)

        return True

    def validate_properties(self):
        """

        Returns:

        """
        # Verify Collection, Experiment and channel
        try:
            self.collection = Collection.objects.get(name=self.config.config_data["database"]["collection"])
            self.experiment = Experiment.objects.get(name=self.config.config_data["database"]["experiment"],
                                                     collection=self.collection)
            self.channel_layer = ChannelLayer.objects.get(name=self.config.config_data["database"]["channel_layer"],
                                                          experiment=self.experiment)
            self.resolution = self.channel_layer.base_resolution

        except Collection.DoesNotExist:
            raise BossError("Collection {} not found".format(self.collection), ErrorCodes.RESOURCE_NOT_FOUND)
        except Experiment.DoesNotExist:
            raise BossError("Experiment {} not found".format(self.experiment), ErrorCodes.RESOURCE_NOT_FOUND)
        except ChannelLayer.DoesNotExist:
            raise BossError("Channel or Layer {} not found".format(self.channel_layer), ErrorCodes.RESOURCE_NOT_FOUND)

        # TODO If channel already exists, check corners to see if data exists.  If so question user for overwrite
        # TODO Check tile size - error if too big
        return True

    def setup_ingest(self, creator, config_data):
        """

        Args:


        Returns:

        """
        # Validate config data and schema

        self.owner = creator
        try:
            valid_schema = self.validate_config_file(config_data)
            valid_prop = self.validate_properties()
            if valid_schema is True and valid_prop is True:
                # create the django model for the job
                self.job = self.create_ingest_job()

                # create the additional resources needed for the ingest
                # initialize the ndingest project for use with the library
                proj_class = BossIngestProj.load()
                self.nd_proj = proj_class(self.collection.name, self.experiment.name, self.channel_layer.name,
                                          self.resolution, self.job.id)

                # Create the upload queue
                upload_queue = self.create_upload_queue()
                self.job.upload_queue = upload_queue.url

                # Create the ingest queue
                ingest_queue = self.create_ingest_queue()
                self.job.ingest_queue = ingest_queue.url

                self.generate_upload_tasks()
                tile_bucket = TileBucket(self.job.collection + '&' + self.job.experiment)

                self.create_ingest_credentials(upload_queue, tile_bucket)

                # Update status
                self.job.status = 1
                self.job.save()

            # TODO create channel if needed

        except BossError as err:
            raise BossError(err.message, err.error_code)
        except Exception as e:
            raise BossError("Unable to create the upload and ingest queue.{}".format(e),
                            ErrorCodes.BOSS_SYSTEM_ERROR)
        return self.job

    def create_ingest_job(self):
        """

        Returns:

        """

        ingest_job_serializer_data = {
            'creator': self.owner,
            'collection': self.collection.name,
            'experiment': self.experiment.name,
            'channel_layer': self.channel_layer.name,
            'config_data': json.dumps(self.config.config_data),
            'resolution': self.resolution,
            'x_start': self.config.config_data["ingest_job"]["extent"]["x"][0],
            'x_stop': self.config.config_data["ingest_job"]["extent"]["x"][1],
            'y_start': self.config.config_data["ingest_job"]["extent"]["y"][0],
            'y_stop': self.config.config_data["ingest_job"]["extent"]["y"][1],
            'z_start': self.config.config_data["ingest_job"]["extent"]["z"][0],
            'z_stop': self.config.config_data["ingest_job"]["extent"]["z"][1],
            't_start': self.config.config_data["ingest_job"]["extent"]["t"][0],
            't_stop': self.config.config_data["ingest_job"]["extent"]["t"][1],
            'tile_size_x': self.config.config_data["ingest_job"]["tile_size"]["x"],
            'tile_size_y': self.config.config_data["ingest_job"]["tile_size"]["y"],
            'tile_size_z': self.config.config_data["ingest_job"]["tile_size"]["z"],
            'tile_size_t': self.config.config_data["ingest_job"]["tile_size"]["t"],
        }
        serializer = IngestJobCreateSerializer(data=ingest_job_serializer_data)
        if serializer.is_valid():
            ingest_job = serializer.save()
            return ingest_job

        else:
            raise BossError("{}".format(serializer.errors), ErrorCodes.SERIALIZATION_ERROR)

    def get_ingest_job(self, ingest_job_id):
        """

        Args:
            ingest_job_id:

        Returns:

        """
        try:
            ingest_job = IngestJob.objects.get(id=ingest_job_id)
            return ingest_job
        except IngestJob.DoesNotExist:
            raise BossError("The ingest job with id {} does not exist".format(str(ingest_job_id)),
                            ErrorCodes.OBJECT_NOT_FOUND)

    def delete_ingest_job(self, ingest_job_id):
        """

        Args:
            ingest_job_id:

        Returns:

        """
        try:

            # delete ingest job
            ingest_job = IngestJob.objects.get(id=ingest_job_id)
            proj_class = BossIngestProj.load()
            self.nd_proj = proj_class(ingest_job.collection, ingest_job.experiment, ingest_job.channel_layer,
                                      ingest_job.resolution, ingest_job.id)

            # delete the ingest and upload_queue
            self.delete_upload_queue()
            self.delete_ingest_queue()

            # delete any pending entries in the tile index database and tile bucket
            self.delete_tiles(ingest_job)

            ingest_job.status = 3
            ingest_job.save()

            # Remove ingest credentials for a job
            self.remove_ingest_credentials(ingest_job_id)

        except Exception as e:
            raise BossError("Unable to delete the upload queue.{}".format(e), ErrorCodes.BOSS_SYSTEM_ERROR)
        except IngestJob.DoesNotExist:
            raise BossError("Ingest job with id {} does not exist".format(ingest_job_id), ErrorCodes.OBJECT_NOT_FOUND)
        return ingest_job_id

    def create_upload_queue(self):
        """

        Returns:

        """
        UploadQueue.createQueue(self.nd_proj, endpoint_url=None)
        queue = UploadQueue(self.nd_proj, endpoint_url=None)
        return queue

    def create_ingest_queue(self):
        """

        Returns:

        """
        IngestQueue.createQueue(self.nd_proj, endpoint_url=None)
        queue = IngestQueue(self.nd_proj, endpoint_url=None)
        return queue

    def delete_upload_queue(self):
        """

        Returns:

        """
        UploadQueue.deleteQueue(self.nd_proj, endpoint_url=None)

    def delete_ingest_queue(self):
        """

        Returns:

        """
        IngestQueue.deleteQueue(self.nd_proj, endpoint_url=None)

    def get_tile_bucket(self):
        """

        Returns:

        """
        return TileBucket.getBucketName()

    def generate_upload_tasks(self, job_id=None):
        """

        Args:
            job_id:

        Returns:

        """

        if job_id is None and self.job is None:
            raise BossError("Unable to generate upload tasks for the ingest service. Please specify a ingest job",
                            ErrorCodes.UNABLE_TO_VALIDATE)
        elif job_id:
            # Using the job id to get the job
            try:
                ingest_job = IngestJob.objects.get(id=job_id)
            except IngestJob.DoesNotExist:
                raise BossError("Ingest job with id {} does not exist".format(job_id), ErrorCodes.RESOURCE_NOT_FOUND)
        else:
            ingest_job = self.job

        # Generate upload tasks for the ingest job
        # Get the project information
        bosskey = ingest_job.collection + CONNECTER + ingest_job.experiment + CONNECTER + ingest_job.channel_layer
        lookup_key = (LookUpKey.get_lookup_key(bosskey)).lookup_key
        [col_id, exp_id, ch_id] = lookup_key.split('&')
        project_info = [col_id, exp_id, ch_id]

        for time_step in range(ingest_job.t_start, ingest_job.t_stop, 1):
            # For each time step, compute the chunks and tile keys

            for z in range(ingest_job.z_start, ingest_job.z_stop, 16):
                for y in range(ingest_job.y_start, ingest_job.y_stop, ingest_job.tile_size_y):
                    for x in range(ingest_job.x_start, ingest_job.x_stop, ingest_job.tile_size_x):

                        # compute the chunk indices
                        chunk_x = int(x/ingest_job.tile_size_x)
                        chunk_y = int(y/ingest_job.tile_size_y)
                        chunk_z = int(z/16)

                        # Compute the number of tiles in the chunk
                        if ingest_job.z_stop-z >= 16:
                            num_of_tiles = 16
                        else:
                            num_of_tiles = ingest_job.z_stop-z

                        # Generate the chunk key
                        chunk_key = (BossBackend(self.config)).encode_chunk_key(num_of_tiles, project_info,
                                                                                ingest_job.resolution,
                                                                                chunk_x, chunk_y, chunk_z, time_step)
                        # get the tiles keys for this chunk
                        for tile in range(0, num_of_tiles):
                            # get the tile key
                            tile_key = (BossBackend(self.config)).encode_tile_key(project_info, ingest_job.resolution,
                                                                                  chunk_x, chunk_y, tile, time_step)

                            # Generate the upload task msg
                            msg = self.create_upload_task_message(ingest_job.id, chunk_key, tile_key,
                                                                  ingest_job.upload_queue, ingest_job.ingest_queue)

                            # Upload the message
                            self.send_upload_task_message(msg)

    @staticmethod
    def create_upload_task_message(job_id, chunk_key, tile_key, upload_queue_arn, ingest_queue_arn):
        """

        Args:
            job_id:
            chunk_key:
            tile_key:
            upload_queue_arn:
            ingest_queue_arn:

        Returns:

        """
        msg = {}
        msg['job_id'] = job_id
        msg['chunk_key'] = chunk_key
        msg['tile_key'] = tile_key
        msg['upload_queue_arn'] = upload_queue_arn
        msg['ingest_queue_arn'] = ingest_queue_arn
        return json.dumps(msg)

    def send_upload_task_message(self, msg):
        """

        Args:
            msg:

        Returns:

        """
        queue = UploadQueue(self.nd_proj, endpoint_url=None)
        queue.sendMessage(msg)

    def delete_tiles(self, ingest_job):
        """
        Delete all remaining tiles from the tile index database and tile bucket
        Args:
            ingest_job: Ingest job model

        Returns:

        """
        try:
            # Get all the chunks for a job
            tiledb = BossTileIndexDB(ingest_job.collection + '&' + ingest_job.experiment)
            tilebucket = TileBucket(ingest_job.collection + '&' + ingest_job.experiment)
            chunks = list(tiledb.getTaskItems(ingest_job.id))

            for chunk in chunks:
                chunk_key = chunk['chunk_key']
                # delete each tile in the chunk
                for key in chunk['tile_uploaded_map']:
                    response = tilebucket.deleteObject(key)
                tiledb.deleteCuboid(chunk['chunk_key'])

        except Exception as e:
            raise BossError ("Exception while deleteing tiles for the ingest job {}. {}".format(ingest_job.id,e),
                             ErrorCodes.BOSS_SYSTEM_ERROR)

    def create_ingest_credentials(self, upload_queue, tile_bucket):
        """

        Returns:

        """
        # Generate credentials for the ingest_job
        # Create the credentials for the job
        ingest_creds = IngestCredentials()
        policy = BossUtil.generate_ingest_policy(self.job.id, upload_queue, tile_bucket)
        ingest_creds.generate_credentials(self.job.id, policy.arn)

    def remove_ingest_credentials(self, job_id):
        """
        Remove the ingest credentials for a job
        Args:
            job_id: The id of the ingest job

        Returns:
            status
        """
        # Create the credentials for the job
        ingest_creds = IngestCredentials()
        ingest_creds.remove_credentials(job_id)
        status = BossUtil.delete_ingest_policy(job_id)
        return status
