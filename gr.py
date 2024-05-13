import gradio as gr
from sd import StableDiffusionPipeline
from PIL import Image
import numpy as np
import os
import time
import random
from itertools import permutations
import torch
# from sd.untool import delete_runtime, free_runtime
from model_path import model_path

DEVICE_ID = 0
BASENAME = list(model_path.keys())
print(BASENAME)
scheduler = ["LCM", "DDIM"]

def create_size(*size_elements):
    unique_size_elements = set(size_elements)
    rectangle = list(permutations(unique_size_elements, 2))
    square = [(img_size, img_size) for img_size in unique_size_elements]
    all_img_size = square + rectangle 
    return [(f"{size[0]}:{size[1]}", [size[0], size[1]]) for size in all_img_size]

SIZE = create_size(512, 768)

def seed_torch(seed=1029):
    seed = seed % 4294967296
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)  # 为了禁止hash随机化，使得实验可复现
    np.random.seed(seed)
    torch.manual_seed(seed)
    print("set seed to:", seed)


class ModelManager():
    def __init__(self):
        self.current_model_name = None
        self.pipe = None
        self.size = None
        self.change_model(BASENAME[0], size=[512,512], scheduler=scheduler[0])

    def pre_check(self, model_select, check_type=None):
        check_pass = True
        model_select_path = os.path.join('models', 'basic', model_select)
        te_path = os.path.join(model_select_path, model_path[model_select]['encoder'])
        unet_path = os.path.join(model_select_path, model_path[model_select]['unet'])
        vae_de_path = os.path.join(model_select_path, model_path[model_select]['vae_decoder'])
        vae_en_path = os.path.join(model_select_path, model_path[model_select]['vae_encoder'])

        if "te" in check_type:
            if not os.path.isfile(te_path):
                gr.Warning("No {} text encoder, please download first".format(model_select))
                check_pass = False
                # return False
        if "unet" in check_type:
            if not os.path.isfile(unet_path):
                gr.Warning("No {} unet, please download first".format(model_select))
                check_pass = False

        if "vae" in check_type:
            if not os.path.exists(vae_en_path) or not os.path.exists(vae_de_path):
                gr.Warning("No {} vae, please download first".format(model_select))
                check_pass = False

        return check_pass

    def change_model(self, model_select, size, scheduler, progress=gr.Progress()):
        if self.pipe is None:
            self.pre_check(model_select, check_type=["te", "unet", "vae"])
            self.pipe = StableDiffusionPipeline(
                basic_model=model_select,
                scheduler=scheduler,
                height=size[0],
                width=size[1],
            )
            self.pipe.set_height_width(size[0], size[1])
            self.current_model_name = model_select
            self.size = size
            return

        if self.current_model_name != model_select:
            # change both te and unet
            if self.pre_check(model_select, check_type=["te", "unet", "vae"]):
                try:
                    gr.Info("Loading {} with {}:{} ...".format(model_select, size[0], size[1]))
                    progress(0.4, desc="Loading....")
                    self.pipe.change_lora(model_select)
                    progress(0.8, desc="Loading....")
                    self.pipe.set_height_width(size[0], size[1])
                    progress(1, desc="Loading....")
                    gr.Info("Success load {} LoRa {}:{}".format(model_select, size[0], size[1]))
                    self.current_model_name = model_select
                    self.size = size
                    return model_select, size
                except Exception as e:
                    print(e)
                    gr.Error("{}".format(e))
                    return self.current_model_name, self.size
            else:
                return self.current_model_name, self.size
        else:
            gr.Info("{} LoRa {}:{} have been loaded".format(model_select, size, size))
            self.pipe.set_height_width(size[0], size[1])
            return self.current_model_name, self.size

    def generate_image_from_text(self, text, image=None, step=4, strength=0.5, seed=None, crop=None, scheduler=None):
        img_pil = self.pipe(
            init_image=image,
            prompt=text,
            negative_prompt="low resolution",
            num_inference_steps=step,
            strength=strength,
            scheduler=scheduler,
            guidance_scale=0,
            seeds=[random.randint(0, 1000000) if seed is None else seed]
        )
        if crop == 1:
            h, w = img_pil.size
            print(h, w)
            img_pil = img_pil.crop((1/8*w, 0, 7/8*w, h))
        return img_pil


model_manager = ModelManager()

description = """
# Text-to-Image and Image-to-Image Generator

Generate images that incorporate both text descriptions and uploaded images, allowing you to create unique visual content.
"""

if __name__ == '__main__':
    with gr.Blocks(analytics_enabled=False) as demo:
        with gr.Row():
            gr.Markdown(description)
        with gr.Row():
            with gr.Column():
                input_content = gr.Textbox(lines=1, label="Input content")
                upload_image = gr.Image(sources=['upload', 'webcam', 'clipboard'], type='pil', label="image")
                with gr.Row():
                    num_step = gr.Slider(minimum=3, maximum=20, value=4, step=1, label="Steps", scale=2)
                    denoise = gr.Slider(minimum=0.2, maximum=1.0, value=0.5, step=0.1, label="Denoising Strength",
                                        scale=1)
                with gr.Row():
                    seed_number = gr.Number(value=1, label="seed")
                    crop = gr.Radio(["1:1", "3:4"], label="Crop", type="index", value="1:1")
                    scheduler_type = gr.Dropdown(choices=scheduler, value=scheduler[0], label="Scheduler", interactive=False)
                with gr.Row():
                    clear_bt = gr.ClearButton(value="Clear",
                                              components=[input_content, upload_image, seed_number, denoise,
                                                          num_step])
                    submit_bt = gr.Button(value="Submit", variant="primary")
            with gr.Column():
                with gr.Row():
                    model_select = gr.Dropdown(choices=BASENAME, value=BASENAME[0], label="Model", interactive=True)
                    size = gr.Dropdown(choices=SIZE, value=512, label="Size", interactive=True)
                    change_bt = gr.Button(value="Change", interactive=True)
                out_img = gr.Image(label="Output")

        clear_bt.add(components=[out_img])
        change_bt.click(model_manager.change_model, [model_select, size, scheduler_type], [model_select, size])
        input_content.submit(model_manager.generate_image_from_text,
                             [input_content, upload_image, num_step, denoise, seed_number], [out_img])
        submit_bt.click(model_manager.generate_image_from_text,
                        [input_content, upload_image, num_step, denoise, seed_number, crop, scheduler_type], [out_img])

    # 运行 Gradio 应用
    demo.queue(max_size=10)
    demo.launch(server_port=8999, server_name="0.0.0.0")
