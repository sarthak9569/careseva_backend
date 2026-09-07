const express = require('express');
const router = express.Router();
const Prescription = require('../models/Prescription');
const User = require('../models/User');

// @desc    Get all prescriptions for a user
// @route   GET /api/prescriptions
router.get('/', async (req, res) => {
  try {
    // In a real app, we'd get user ID from auth middleware
    const { userId } = req.query;
    if (!userId) return res.status(400).json({ message: 'User ID is required' });

    const prescriptions = await Prescription.find({ user: userId }).sort({ createdAt: -1 });
    res.json({ success: true, prescriptions });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
});

// @desc    Upload a prescription (Mocked)
// @route   POST /api/prescriptions/upload
router.post('/upload', async (req, res) => {
  const { userId, title, fileName, fileUrl } = req.body;
  try {
    if (!userId || !title) {
      return res.status(400).json({ message: 'User ID and title are required' });
    }

    const prescription = await Prescription.create({
      user: userId,
      title,
      fileName: fileName || 'prescription.pdf',
      fileUrl: fileUrl || 'https://example.com/mock-prescription.pdf'
    });

    res.status(201).json({ success: true, prescription });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
});

// @desc    Delete a prescription
// @route   DELETE /api/prescriptions/:id
router.delete('/:id', async (req, res) => {
  try {
    const prescription = await Prescription.findById(req.params.id);
    if (!prescription) return res.status(404).json({ message: 'Prescription not found' });

    await prescription.deleteOne();
    res.json({ success: true, message: 'Prescription deleted' });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
});

module.exports = router;
