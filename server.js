const express = require('express');
const multer = require('multer');
const axios = require('axios');
const FormData = require('form-data');
const fs = require('fs');
const path = require('path');

const app = express();
const upload = multer({ dest: 'uploads/' });

app.use(express.static('public'));

app.post('/upload', upload.array('images'), async (req, res) => {
    try {
        const processedImages = [];
        for (const file of req.files) {
            const formData = new FormData();
            formData.append('file', fs.createReadStream(file.path));

            const response = await axios.post('http://localhost:5001/remove-background', formData, {
                headers: {
                    ...formData.getHeaders()
                },
                responseType: 'arraybuffer'
            });

            const processedImagePath = `processed/${file.filename}.png`;
            fs.writeFileSync(processedImagePath, response.data);
            processedImages.push(processedImagePath);
            fs.unlinkSync(file.path); // Clean up uploaded file
        }
        res.json({ processedImages });
    } catch (error) {
        console.error('Error processing images:', error);
        res.status(500).send('Error processing images');
    }
});

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// Serve processed images
app.use('/processed', express.static(path.join(__dirname, 'processed')));


if (!fs.existsSync('uploads')) {
    fs.mkdirSync('uploads');
}
if (!fs.existsSync('processed')) {
    fs.mkdirSync('processed');
}

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});
