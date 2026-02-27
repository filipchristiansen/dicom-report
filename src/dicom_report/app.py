import sys
import os

import json
import io
import tempfile
import subprocess
import uuid
from enum import Enum
import base64
from datetime import datetime

from io import BytesIO
from cloudevents.sdk.event import v1

from pydicom.uid import ExplicitVRLittleEndian,generate_uid, UltrasoundImageStorage
from classutils import methods
from dicomutils import element_faker, simulator

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import UID,generate_uid
from pydicom.encaps import encapsulate
from pydicom.filewriter import dcmwrite
from pydicom.dataelem import DataElement
import numpy as np
import pydicom
from PIL import Image, ImageFont, ImageDraw
from pydicom import dcmread


from dapr.clients import DaprClient
from dapr.clients.grpc._state import StateItem
from dapr.clients.grpc._request import TransactionalStateOperation, TransactionOperationType
from dapr.ext.grpc import App, InvokeMethodRequest, InvokeMethodResponse


from dotenv import load_dotenv

load_dotenv()

from intelligynai_common.logging import logger
logg = logger.setup_logger("ReporterLogger", True)

from dicom_report.paths import FONT_DIR, TEMPLATE_DIR


# pub sub setup
DAPR_STORE_NAME = os.environ.get("DAPR_STORE_NAME")
PUBSUB_NAME = os.environ.get("PUBSUB_NAME")
TOPIC_NAME_PREDICTION = os.environ.get("TOPIC_NAME_PREDICTION")
TOPIC_NAME_REPORT = os.environ.get("TOPIC_NAME_REPORT")

REPORT_TEMPLATE = os.environ.get("REPORT_TEMPLATE")

ELEMENTS_TO_SIMULATE = ['PatientID','PatientName']

if os.getenv("REPORT_SIMULATE_ON", 'False').lower() in ('true', '1', 't','yes','y'):
    REPORT_SIMULATE_ON = True
else:
    REPORT_SIMULATE_ON = False

logg.info(f"REPORT_SIMULATE_ON={REPORT_SIMULATE_ON}")


class Diagnosis(Enum):
    def __str__(self):
        return str(self.value)

    BENIGN = 'benign'
    INCONCLUSIVE = 'inconclusive'
    MALIGNANT = 'malignant'


class Dsmethod(Enum):
    def __str__(self):
        return str(self.value)

    REGULAR = 'regular'
    IMG2DCM = 'img2dcm'


class Action(Enum):
    def __str__(self):
        return str(self.value)

    GENERATE = 'generate'
    COPY = 'copy'

def load_json_file(filename):
    """
    Loads a JSON file into a dictionary or list.
    """
    try:
        with open(filename, "r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError:
        logg.error(f"Error: The file '{filename}' contains invalid JSON.")
        sys.exit(1)

def anonymize_word(w):
    n = 2
    if len(w) < 3:
        return w
    return "*" * (len(w) - n) + w[len(w) - n:]


def crop_top_of_image(img, crop_fraction=0.15):
    width, height = img.size

    top_crop = int(height * crop_fraction)
    crop_box = (0, top_crop, width, height)  # (left, upper, right, lower)

    cropped_img = img.crop(crop_box)

    return cropped_img



def publish_result_to_pubsub(data):
    logg.info(f"Publishing results on {PUBSUB_NAME},{TOPIC_NAME_REPORT}")

    jsondata = json.dumps(data)

    with DaprClient() as client:
        #Using Dapr SDK to publish a topic
        result = client.publish_event(
            pubsub_name=PUBSUB_NAME,
            topic_name=TOPIC_NAME_REPORT,
            data=jsondata,
            data_content_type='application/json',
        )

def publish_report_to_statestore(data, report_file, path_statestore):
     logg.info("Publishing results to statestore")
     with DaprClient() as client:


            current_working_folder = os.getcwd()

            logg.info("Current working folder: "  + current_working_folder)

            logg.info("Report image file name: " + report_file)
            # TODO Unique file, never reuse file names


            with open(report_file, "rb") as f:
                image_b64 = base64.b64encode(f.read())
                logg.info(f"Saving blob to state: {path_statestore}")
            logg.info("Report file name read")
            client.save_state(DAPR_STORE_NAME, path_statestore, image_b64)
            logg.info("Report file saved to statestore")



def get_template_as_jpeg(diagnosis):

    with tempfile.TemporaryDirectory() as tmp:
        template_image = Image.open(f'/app/reporter/image/template/rag/{diagnosis.value}.png').convert('RGB')
        main_width, main_height = template_image.size
        tmp_jpeg_path = os.path.join(tmp, f'{diagnosis.value}.jpg')
        template_image.save(tmp_jpeg_path)

    return template_image, main_width, main_height


def use_img2dcm(work_image):

        image_file = f"/app/reporter/data/tmp/report_{uuid.uuid4()}.jpg"

        work_image.save(image_file)

        with tempfile.TemporaryDirectory() as tmp:

            tmp_dicom_path = os.path.join(tmp, f'image.dcm')

            logg.info(f"tmp_dicom_path: {tmp_dicom_path}")

            # Command to run
            command = ["img2dcm", image_file,tmp_dicom_path]

            command_as_text = " ".join(command)
            logg.info(command_as_text)

            # Run the command
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Get the output and error (if any)
            output, error = process.communicate()

        # Print the output and error
        #logg.info("Output:", output.decode())
        #logg.info("Error:", error.decode())
        #sys.stdout.flush()

            ds = dcmread(tmp_dicom_path)

        return ds

def ds_factory(ds_method, work_image):
    if ds_method == Dsmethod.IMG2DCM:
        return use_img2dcm(work_image)
    else:
        return Dataset()

def save_dicom_file(ds, filename):
    ds.save_as(filename)

    #output_file_path2 = 'output/report_ybr_full_422_2.dcm'
    #dcmwrite(output_file_path2, ds)


def dataelement_to_string(element):
    """Convert pydicom DataElement to a readable string."""
    if element is None:
        return "None"
    value = element.value
    return ", ".join(map(str, value)) if isinstance(value, (list, tuple)) else str(value)


def generate_bare_dicom_file(diagnosis, thumbs):


    logg.info("Generating DICOM File Start")
    #logg.info(json.dumps(elements, indent=4), flush=True)  # Pretty-print JSON

    faker = element_faker.ElementFaker()
    logg.info("Faker declared")

    # sop instance is special as it needs to match between ds and meta_data
    SOP_Instance_UID = generate_uid()

    work_image, main_width, main_height = get_template_as_jpeg(diagnosis)

    x_offset_text = 50

    title_font = ImageFont.truetype(f'font/RobotoMono-Bold.ttf', 70)
    watermark_font = ImageFont.truetype(f'font/RobotoMono-Bold.ttf', 140)


    #timestamp_output = f"{timestamp}"

    image_editable = ImageDraw.Draw(work_image)

    #Starting Coordinates: Pillow library uses a Cartesian pixel coordinate system, with (0,0) in the upper left corner.
    #Text: String between single or double quotations
    #Text color in RGB format: Google Picker is a great resource to find the best color. Search “Color Picker” on Google and it will show up.
    #Font style: Google Fonts is a great resource to pick your font style, and you can also download the TTF(TrueType Font) file of the font family.
    image_editable.text((x_offset_text,2), "DEMO PATIENT ID", (255, 255, 255), font=title_font)
    #image_editable.text((x_offset_text,87), study_id_output + f" , # of images used: {len(thumbs)}", (255, 255, 255), font=title_font)
    image_editable.text((x_offset_text,87), "DEMO STUDY INSTANCE ID", (255, 255, 255), font=title_font)
    image_editable.text((x_offset_text,172), "DEMO SERIES INSTANCE ID", (255, 255, 255), font=title_font)
    #image_editable.text((x_offset_text,257), series_instance_uid_output, (255, 255, 255), font=title_font)


    image_editable.text((200,1300), "Demo Purposes Only, Not For Diagnostic Use",  (203,201,201), font=title_font)


    images = 0
    thumbnails = []

    # Define thumbnail size
    thumb_width = int(main_width / 8)
    thumb_height = int(thumb_width * 0.75)  # Adjust aspect ratio as needed

    for thumb in thumbs:
        #thumb = Image.open(path).convert('RGB')
        thumb = thumb.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        thumbnails.append(thumb)

    # Step 4: Calculate positions to paste thumbnails evenly
    total_thumbs = len(thumbnails)
    space_between = (int(main_width * 0.6) - (total_thumbs * thumb_width)) // (total_thumbs + 1)
    y_position = main_height * 2 // 3  # Lower third of the image

    # Step 5: Paste thumbnails
    x_offset = space_between
    for thumb in thumbnails:
        cropped = crop_top_of_image(thumb)
        work_image.paste(cropped, (x_offset, y_position))
        x_offset += thumb_width + space_between




    ds = ds_factory(Dsmethod.IMG2DCM,work_image)
    file_meta = FileMetaDataset()
    ds.SOPInstanceUID = SOP_Instance_UID
    file_meta.MediaStorageSOPInstanceUID = SOP_Instance_UID

    file_meta_group_length = sum(
    len(file_meta[tag].value) + 12 for tag in file_meta.keys() if tag.group == 2
    )
    file_meta.FileMetaInformationGroupLength = file_meta_group_length
    ds.file_meta = file_meta

    logg.info("Generating DICOM File End")

    return ds, work_image


def generate_dicom_file(ds_method, elements, diagnosis, ds_source, thumbs):


    logg.info("Generating DICOM File Start")
    #logg.info(json.dumps(elements, indent=4), flush=True)  # Pretty-print JSON

    faker = element_faker.ElementFaker()
    sim = simulator.TestData()
    logg.info("Faker declared")

    # sop instance is special as it needs to match between ds and meta_data
    SOP_Instance_UID = generate_uid()

    for element in elements:
        action = element.get('action',Action.GENERATE)
        element_name = element['name']
        default_value = element.get('default_value',None)
        type =  element.get('type','regular')
        if action == Action.COPY.value:
            element_value = ds_source[element_name]
        else:
            element_value = methods.call_method(faker,element_name,default_value)


        if isinstance(element_value, DataElement):
            evalue = dataelement_to_string(element_value)
        else:
            evalue =  element_value

        if type == 'meta':
            pass
        else:
            if element_name == "PatientID":
                logg.info("PatientID")
                patient_id_output = f"Patient id: {anonymize_word(evalue)}"
                #patient_id_output = f"Patient id: ****"
                logg.info("PatientID End")

            if element_name == "StudyID":
                logg.info("StudyID")
                study_id_output = f"Study id: {evalue}"
                logg.info("StudyID End")

            if element_name == "StudyInstanceUID":
                logg.info("Study Instance UID")
                study_instance_uid_output = f"Study Instance UID: {evalue}"
                logg.info("Study Instance UID End")

            if element_name == "SeriesInstanceUID":
                logg.info("SeriesInstanceUID")
                series_instance_uid_output = f"Series Instance UID: {evalue}"
                logg.info("SeriesInstanceUID End")




    work_image, main_width, main_height = get_template_as_jpeg(diagnosis)

    x_offset_text = 50

    title_font = ImageFont.truetype(f'font/RobotoMono-Bold.ttf', 70)
    watermark_font = ImageFont.truetype(f'font/RobotoMono-Bold.ttf', 140)


    #timestamp_output = f"{timestamp}"

    image_editable = ImageDraw.Draw(work_image)

    #Starting Coordinates: Pillow library uses a Cartesian pixel coordinate system, with (0,0) in the upper left corner.
    #Text: String between single or double quotations
    #Text color in RGB format: Google Picker is a great resource to find the best color. Search “Color Picker” on Google and it will show up.
    #Font style: Google Fonts is a great resource to pick your font style, and you can also download the TTF(TrueType Font) file of the font family.
    image_editable.text((x_offset_text,2), patient_id_output, (255, 255, 255), font=title_font)
    #image_editable.text((x_offset_text,87), study_id_output + f" , # of images used: {len(thumbs)}", (255, 255, 255), font=title_font)
    image_editable.text((x_offset_text,87), study_instance_uid_output, (255, 255, 255), font=title_font)
    image_editable.text((x_offset_text,172), series_instance_uid_output, (255, 255, 255), font=title_font)
    #image_editable.text((x_offset_text,257), series_instance_uid_output, (255, 255, 255), font=title_font)


    image_editable.text((200,1300), "Demo Purposes Only, Not For Diagnostic Use",  (203,201,201), font=title_font)


    images = 0
    thumbnails = []

    # Define thumbnail size
    thumb_width = int(main_width / 8)
    thumb_height = int(thumb_width * 0.75)  # Adjust aspect ratio as needed

    for thumb in thumbs:
        #thumb = Image.open(path).convert('RGB')
        thumb = thumb.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        thumbnails.append(thumb)

    # Step 4: Calculate positions to paste thumbnails evenly
    total_thumbs = len(thumbnails)
    space_between = (int(main_width * 0.6) - (total_thumbs * thumb_width)) // (total_thumbs + 1)
    y_position = main_height * 2 // 3  # Lower third of the image

    # Step 5: Paste thumbnails
    x_offset = space_between
    for thumb in thumbnails:
        cropped = crop_top_of_image(thumb)
        work_image.paste(cropped, (x_offset, y_position))
        x_offset += thumb_width + space_between




    ds = ds_factory(ds_method,work_image)
    file_meta = FileMetaDataset()
    ds.SOPInstanceUID = SOP_Instance_UID
    file_meta.MediaStorageSOPInstanceUID = SOP_Instance_UID

    for element in elements:
        action = element.get('action',Action.GENERATE)
        element_name = element['name']
        default_value = element.get('default_value',None)
        type =  element.get('type','regular')
        if action == Action.COPY.value:
            logg.info(f"COPY ACTION, {element_name},{REPORT_SIMULATE_ON},{ELEMENTS_TO_SIMULATE}")
            if REPORT_SIMULATE_ON and element_name in ELEMENTS_TO_SIMULATE:
                element_value = methods.call_method(sim,element_name,default_value)
            else:
                element_value = ds_source[element_name]
        else:
            logg.info(f"OTHER ACTION, {element_name},{REPORT_SIMULATE_ON},{ELEMENTS_TO_SIMULATE}")
            if REPORT_SIMULATE_ON and element_name in ELEMENTS_TO_SIMULATE:
                element_value = methods.call_method(sim,element_name,default_value)
            else:
                element_value = methods.call_method(faker,element_name,default_value)

        if type == 'meta':
            setattr(file_meta, element_name, element_value)
        else:
            if isinstance(element_value, DataElement):
                value_to_set = dataelement_to_string(element_value)
                setattr(ds, element_name, value_to_set)
            else:
                setattr(ds, element_name, element_value)

    file_meta_group_length = sum(
    len(file_meta[tag].value) + 12 for tag in file_meta.keys() if tag.group == 2
    )
    file_meta.FileMetaInformationGroupLength = file_meta_group_length
    ds.file_meta = file_meta


    if ds_method == Dsmethod.REGULAR:
        logg.info(Dsmethod.REGULAR)
        #ds = patch_image_ybr_to_ds_from_png_template(ds,diagnosis)
    else:
        logg.info("OTHER")

    logg.info("Generating DICOM File End")

    return ds, work_image


def create_report(data):

    patient_id = data.get('patient_id')
    study_id = data.get('study_id')
    study_instance_uid = data.get('study_instance_uid')
    series_instance_uid = data.get('series_instance_uid')
    diagnosis = Diagnosis(data.get('prediction'))

    timestamp = data.get('timestamp')
    studyinstanceuid = data.get('studyinstanceuid')
    seriesinstanceuid = data.get('seriesinstanceuid')


    # convert to jpeg
    my_image_p = Image.open(f"image/{diagnosis.value}.png")
    rgb_im = my_image_p.convert('RGB')
    rgb_im.save(f'{diagnosis.value}.jpg')


    my_image = Image.open(f"{diagnosis.value}.jpg")

    title_font = ImageFont.truetype(f'font/Roboto-Regular.ttf', 70)

    patient_id_output = f"Patient id: {anonymize_word(patient_id)}"
    study_id_output = f"study id: {study_id}"
    study_instance_uid_output = f"study instance uid: {study_instance_uid}"
    series_instance_uid_output = f"series instance uid: {series_instance_uid}"
    timestamp_output = f"{timestamp}"

    image_editable = ImageDraw.Draw(my_image)

    #Starting Coordinates: Pillow library uses a Cartesian pixel coordinate system, with (0,0) in the upper left corner.
    #Text: String between single or double quotations
    #Text color in RGB format: Google Picker is a great resource to find the best color. Search “Color Picker” on Google and it will show up.
    #Font style: Google Fonts is a great resource to pick your font style, and you can also download the TTF(TrueType Font) file of the font family.
    image_editable.text((750,15), patient_id_output, (237, 230, 211), font=title_font)
    image_editable.text((750,100), study_id_output, (237, 230, 211), font=title_font)
    image_editable.text((750,185), study_instance_uid_output, (237, 230, 211), font=title_font)
    image_editable.text((750,270), timestamp_output, (237, 230, 211), font=title_font)



    my_image.save("report.jpg")

"""
def render_data_in_image(diagnosis):

    study_date = datetime.today().strftime('%Y-%m-%d')
    study_date_dicom = datetime.today().strftime('%Y%m%d')
    study_time = datetime.today().strftime('%H-%M-%S')
    study_time_dicom = datetime.today().strftime('%H%M%S') + ".000000"


    id = f'{patient_id}_{study_id}_{study_date}_{study_time}'
    logg.info(id)


    # convert to jpeg
    template_image = Image.open(f"image/template/{REPORT_TEMPLATE}/{diagnosis}.png")
    jpeg_image = template_image.convert('RGB')

    with tempfile.TemporaryDirectory() as tmp:
        tmp_jpeg_path = os.path.join(tmp, f'{diagnosis}.jpg')
        jpeg_image.save(tmp_jpeg_path)
        work_image = Image.open(tmp_jpeg_path)



        #title_font = ImageFont.truetype(f'font/Roboto-Regular.ttf', 70)
        title_font = ImageFont.truetype(f'font/RobotoMono-Bold.ttf', 70)
        watermark_font = ImageFont.truetype(f'font/RobotoMono-Bold.ttf', 140)

        patient_id_output = f"Patient id: {anonymize_word(patient_id)}"
        study_id_output = f"Study id: {study_id}"
        study_instance_uid_output = f"Study Instance UID: {study_instance_uid}"
        series_instance_uid_output = f"Series Instance UID: {series_instance_uid}"
        timestamp_output = f"{timestamp}"

        image_editable = ImageDraw.Draw(work_image)

        #Starting Coordinates: Pillow library uses a Cartesian pixel coordinate system, with (0,0) in the upper left corner.
        #Text: String between single or double quotations
        #Text color in RGB format: Google Picker is a great resource to find the best color. Search “Color Picker” on Google and it will show up.
        #Font style: Google Fonts is a great resource to pick your font style, and you can also download the TTF(TrueType Font) file of the font family.
        image_editable.text((2,5), patient_id_output, (255, 255, 255), font=title_font)
        image_editable.text((2,90), study_id_output + f" , # of images used: {len(thumbs)}", (255, 255, 255), font=title_font)
        image_editable.text((2,175), study_instance_uid_output, (255, 255, 255), font=title_font)
        image_editable.text((2,260), timestamp_output, (255, 255, 255), font=title_font)


        image_editable.text((200,1300), "Demo Purposes Only, Not For Diagnostic Use",  (203,201,201), font=title_font)



        x_offset = 100
        images = 0
        for thumb in thumbs:
            if images > 3:
                break
            work_image.paste(thumb, (x_offset,1500))
            x_offset = x_offset + 800
            images = images + 1

        image_file = f"data/report_{id}.jpg"

        work_image.save(image_file)


        with open(image_file, "rb") as f:
            jpeg_data = f.read()

        encapsulated_pixel_data = encapsulate([jpeg_data])

        tmp_dicom_path = os.path.join(tmp, f'image.dcm')


        # Command to run
        command = ["img2dcm", image_file,tmp_dicom_path]

        command_as_text = " ".join(command)
        logg.info(command_as_text)

        # Run the command
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Get the output and error (if any)
        output, error = process.communicate()

        # Print the output and error
        #logg.info("Output:", output.decode())
        #logg.info("Error:", error.decode())
        #sys.stdout.flush()

        ds = dcmread(tmp_dicom_path)
        #ds = Dataset()

        #ds = add_file_meta_data(ds)

        ds = add_meta_data(ds)

        # TODO FIX FORMAT

        logg.info("TIME")

        strtime = str(study_time_dicom)[0:6]
        logg.info(strtime)

        ds.StudyDate = study_date_dicom
        ds.StudyTime = strtime

        ds.SeriesDate = study_date_dicom
        ds.SeriesTime = strtime
        ds.ContentTime = strtime

        ds[0x0008, 0x0016].value = "1.2.840.10008.5.1.4.1.1.6.1"


        logg.info("All metadata set")

        dicom_file = f'data/report_{id}.dcm'

        ds.save_as(dicom_file)

"""


app = App()
#Subscribe to a topic


@app.subscribe(pubsub_name=PUBSUB_NAME, topic=TOPIC_NAME_PREDICTION)
def mytopic(event: v1.Event) -> None:
    data = json.loads(event.Data())
    logg.info('Reporter started')
    logg.info('Subscriber data received:')
    logg.info(data)


    calling_type = data.get('calling_type')
    calling_aet = data.get('calling_aet')
    patient_id = data.get('patient_id')
    study_id = data.get('study_id')
    study_instance_uid = data.get('study_instance_uid')
    series_instance_uid = data.get('series_instance_uid')
    dicom_path = data.get('dicom_path')


    diagnosis = Diagnosis(data.get('prediction'))



    timestamp = data.get('timestamp')
    email = data.get('email')
    file_id = data.get('file_id')

    diagnostic_report_link_uid = data.get("diagnostic_report_link_uid","")


    common_attributes ={'calling_type':calling_type,"calling_aet":calling_aet,'patient_id': patient_id, 'study_id': study_id, 'study_instance_uid': study_instance_uid,'series_instance_uid': series_instance_uid}
    logg.info(calling_type, extra=common_attributes)
    logg.info(calling_aet, extra=common_attributes)
    logg.info(patient_id, extra=common_attributes)
    logg.info(study_id, extra=common_attributes)
    logg.info(study_instance_uid, extra=common_attributes)
    logg.info(series_instance_uid, extra=common_attributes)
    logg.info(diagnosis.value, extra=common_attributes)
    logg.info(timestamp, extra=common_attributes)
    logg.info(email, extra=common_attributes)
    logg.info(file_id, extra=common_attributes)
    if not data['image_paths']:
        #TODO log error
        logg.error("No images in submission", extra=common_attributes)
        logg.error('REPORTER ENDED ===================')
        return
    else:
        logg.info('Images in submission')


    image_paths = data['image_paths']
    #image_paths = image_paths.split(",")
    thumbs = []
    imageid = 0
    for image_path in image_paths:
        logg.info(image_path)
        with DaprClient() as client:
            result = client.get_state(DAPR_STORE_NAME, image_path)
            img_b64 = result.data
            img = Image.open(BytesIO(base64.b64decode(img_b64))) #.convert("RGB")
            #img.save(f"test{imageid}.jpg")
            #img.thumbnail((1024, 1024))
            thumbs.append(img)
            imageid = imageid + 1

    logg.info('All thumbs read')
    # TODO render thumbnails and data into image

    logg.info('Reading ds and metadata command template')
    template_filename = "data/dicom_templates/viewpoint.json"
    elements = load_json_file(template_filename)
    found_copy_action = any(item.get("action") == "copy" for item in elements)
    if found_copy_action and calling_type != "EMAIL":
        logg.info('Found copy action')

        #dicom_source_file = get_dicom_source_file()
        #ds_source = pydicom.dcmread(dicom_source_file)
        with DaprClient() as client:
            logg.info(f'dicom_path: {dicom_path[0]}')
            result = client.get_state(DAPR_STORE_NAME, dicom_path[0])
            logg.info(f'result fetched from redis')
            dicom_b64 = result.data
            logg.info(f'dicom_b64 result')
            ds_source = pydicom.dcmread(BytesIO(base64.b64decode(dicom_b64)))
            logg.info(f'read dicom from base 64 string')
    else:
        ds_source = None

    output_filename_base = "report"

    # todo unique file name, never reuse file names
    output_filename_img2dcm = f'/app/reporter/data/output/{output_filename_base}_{Dsmethod.IMG2DCM}.dcm'
    output_filename_jpeg = f'/app/reporter/data/output/{output_filename_base}_{Dsmethod.IMG2DCM}.jpg'

    logg.info(f'output_filename_img2dcm: {output_filename_img2dcm}')
    logg.info(f'output_filename_jpeg: {output_filename_jpeg}')


    if calling_type != "EMAIL":
        dsImg2dcm, report_image = generate_dicom_file(Dsmethod.IMG2DCM, elements, diagnosis, ds_source, thumbs)
    else:
        dsImg2dcm, report_image = generate_bare_dicom_file(diagnosis, thumbs)

    save_dicom_file(dsImg2dcm, output_filename_img2dcm)
    report_image.save(output_filename_jpeg)


    logg.info("Current File Id is ", extra=common_attributes)
    logg.info(file_id)
    if file_id is None:
        path_statestore_directlink_dicom = os.path.normpath(os.path.join("directlink", data.get('patient_id'),data.get('study_id'), "dicom")
                )
    else:
        path_statestore_directlink_dicom = os.path.normpath(os.path.join("directlink", file_id, "dicom")
                )


    path_statestore_dicom = os.path.normpath(os.path.join(data.get('patient_id'),data.get('study_id'), "report", output_filename_img2dcm
            ))
    path_statestore_image = os.path.normpath(os.path.join(data.get('patient_id'),data.get('study_id'), "report", output_filename_jpeg
            ))

    logg.info('Reporting to statestore', extra=common_attributes)

    publish_report_to_statestore(data, output_filename_img2dcm, path_statestore_directlink_dicom)
    if diagnostic_report_link_uid:
        logg.info(f"Diagnostic_report_link_uid published. {diagnostic_report_link_uid}")
        publish_report_to_statestore(data, output_filename_img2dcm, f"diagnostic_report_link_uid/{diagnostic_report_link_uid}")
    else:
        logg.info("No diagnostic_report_link_uid published.")

    publish_report_to_statestore(data, output_filename_img2dcm, path_statestore_dicom)
    publish_report_to_statestore(data, output_filename_jpeg, path_statestore_image)

    data['report_dicom'] = path_statestore_dicom
    data['report_image'] = path_statestore_image
    data['report_directlink'] = path_statestore_directlink_dicom

    logg.info(f'Publishing to: {TOPIC_NAME_REPORT}', extra=common_attributes)
    logg.info(data)

    publish_result_to_pubsub(data)

    # todo shell out and send with pynetdicom unit or send ny ae
    logg.info('Reporter ended', extra=common_attributes)


logg.info(f"Subscribing: {PUBSUB_NAME}, {TOPIC_NAME_PREDICTION}")
app.run(6004)
logg.info(f"Stopping: {PUBSUB_NAME}, {TOPIC_NAME_PREDICTION}")