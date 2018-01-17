import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import roc_auc_score
from torch.autograd import Variable
import pandas as pd
import numpy as np
import torchvision
from torchvision import datasets, models, transforms
from torch.utils.data import Dataset, DataLoader
import torch.utils.model_zoo as model_zoo
import time
import os
import random
from PIL import Image


use_gpu = torch.cuda.is_available
data_dir = "./images"
save_dir = "./savedModels"
label_path = {'train':"./Train_Label.csv", 'val':"./Val_Label.csv", 'test':"Test_Label.csv"}


class CXRDataset(Dataset):

    def __init__(self, csv_file, root_dir, transform = None):
        self.labels_csv = pd.read_csv(csv_file, header=0)
        self.root_dir = root_dir
        self.transform = transform
        self.classes = pd.read_csv(csv_file, header=None,nrows=1).ix[0, :].as_matrix()
        self.classes = self.classes[1:]

    def __len__(self):
        return len(self.labels_csv)

    def __getitem__(self, idx):
        img_name = os.path.join(self.root_dir, self.labels_csv.ix[idx, 0])
        image = Image.open(img_name).convert('RGB')

        if self.transform:
            image = self.transform(image)
        label = self.labels_csv.ix[idx, 1:].as_matrix().astype('float')
        label = torch.from_numpy(label).type(torch.FloatTensor)
        sample = {'image': image, 'label': label}

        return sample

def loadData(batch_size):
    trans = torchvision.transforms.Compose([torchvision.transforms.ToTensor()])
    image_datasets = {x: CXRDataset(label_path[x], data_dir, transform = trans)for x in ['val']}
    dataloders = {x: torch.utils.data.DataLoader(image_datasets[x], batch_size=batch_size, shuffle=False, num_workers=4)
                  for x in ['val']}
    dataset_sizes = {x: len(image_datasets[x]) for x in ['val']}
    print('Validation data: {}'.format(dataset_sizes['val']))

    class_names = image_datasets['val'].classes
    return dataloders, dataset_sizes, class_names

def test_model(model):
    batch_size = 24
    since = time.time()
    dataloders, dataset_sizes, class_names = loadData(batch_size)


    model.train(False)  # Set model to evaluate mode

    outputList = []
    labelList = []
    num=0
    # Iterate over data.
    for idx, data in enumerate(dataloders['val']):
        # get the inputs
        inputs = data['image']
        labels = data['label']

        #wrap them in Variable
        if use_gpu:
            inputs = Variable(inputs.cuda(), volatile=True)
            labels = Variable(labels.cuda(), volatile=True)
        else:
            inputs, labels = Variable(inputs, volatile=True), Variable(labels, volatile=True)
                
        outputs = model(inputs)
        out_data = outputs.data

        labels = labels.data.cpu().numpy()
        out_data = out_data.cpu().numpy()
        for i in range(out_data.shape[0]):
            outputList.append(out_data[i].tolist())
            labelList.append(labels[i].tolist())
        
        if idx%20 == 0 and idx!=0:
            print('{:.2f}%'.format(100*idx/len(dataloders['val'])), end='\r')

    print('Sample outputs-----------------')
    base = random.randint(0, dataset_sizes['val']-min(30, len(outputList)))
    for i in range(min(30, len(outputList))):
        print('{} output: {}\nlabel: {}\n---------------'.format(i+base, ['{:.4f}'.format(item) for item in outputList[i+base]], labelList[i+base]))
                
    epoch_auc_ave = roc_auc_score(np.array(labelList), np.array(outputList))
    epoch_auc = roc_auc_score(np.array(labelList), np.array(outputList), average=None)

    print('AUC: {:.4f}'.format(epoch_auc_ave))
    print()
    for i, c in enumerate(class_names):
        print('{}: {:.4f} '.format(c, epoch_auc[i]))
    print()

class Model(nn.Module):
    def __init__(self):
        super(Model, self).__init__()
        self.model_ft = models.resnet50(pretrained=True)
        for param in self.model_ft.parameters():
            param.requires_grad = False

        self.transition = nn.Sequential(
            nn.Conv2d(2048, 2048, kernel_size=3, padding=1, stride=1, bias=False),
        )
        self.globalPool = nn.Sequential(
            nn.MaxPool2d(32)
        )
        self.prediction = nn.Sequential(
            nn.Linear(2048, 14),
            nn.Sigmoid()
        )

    def forward(self, x):
        x = self.model_ft.conv1(x)
        x = self.model_ft.bn1(x)
        x = self.model_ft.relu(x)
        x = self.model_ft.maxpool(x)

        x = self.model_ft.layer1(x)
        x = self.model_ft.layer2(x)
        x = self.model_ft.layer3(x)
        x = self.model_ft.layer4(x)


        x = self.transition(x)
        x = self.globalPool(x)
        x = x.view(x.size(0), -1)
        x = self.prediction(x)#14
        return x


if __name__ == '__main__':
    model = Model()
    if use_gpu:
        model = model.cuda()
        #model = torch.nn.DataParallel(model).cuda()
    model.load_state_dict(torch.load(os.path.join(save_dir, "resnet50.pth"))) 
    model = test_model(model.cuda())

