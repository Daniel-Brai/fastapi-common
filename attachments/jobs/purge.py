from sqlalchemy_file.storage import StorageManager

from lib.attachments.exceptions import AttachmentError
from lib.jobs import BaseJob


class PurgeAttachmentJob(BaseJob):
    """
    Deletes a single file from object storage by its composite path ('{upload_storage}/{file_id}').

    Used for both primary blobs and ThumbnailGenerator-produced thumbnails

    Enqueued by AttachedOne.schedule_purge() and AttachedMany.purge_at().
    """

    queue = "attachments"
    max_attempts = 2
    retry_on = (AttachmentError,)

    def perform(self, path: str) -> None:
        try:
            self.logger.info(f"PurgeAttachmentJob: purging {path}")
            result = StorageManager.delete_file(path)
            if result:
                self.logger.debug(f"PurgeAttachmentJob: Purged {path} successfully")
            else:
                raise AttachmentError(f"Failed to purge {path}, possibly file not found")
        except AttachmentError as e:
            self.logger.error(f"PurgeAttachmentJob: AttachmentError purging {path} - {e}")
            raise e
        except Exception as e:
            self.logger.error(f"PurgeAttachmentJob: Error purging {path} - {e}")
            raise AttachmentError.from_exc(e)
