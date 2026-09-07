const express = require('express');
const router = express.Router();
const jwt = require('jsonwebtoken');
const User = require('../models/User');
const Hospital = require('../models/Hospital');
const crypto = require('crypto');
const nodemailer = require('nodemailer');

// @desc    Register a new user
// @route   POST /api/auth/register
router.post('/register', async (req, res) => {
    const { name, email, password, role, hospitalName, hospitalCode, address, city, state, pincode } = req.body;
    try {
      const userExists = await User.findOne({ email });
      if (userExists) return res.status(400).json({ message: 'User already exists' });
  
      const user = await User.create({ 
        name, 
        email, 
        password, 
        role: role || 'patient' 
      });
  
      if (user && role === 'hospital_admin') {
        try {
          await Hospital.create({
            name: hospitalName,
            code: hospitalCode,
            adminId: user._id,
            email: email,
            address: address || 'Pending Update',
            city: city || 'Pending Update',
            state: state || 'Pending Update',
            pincode: pincode || '000000'
          });
        } catch (hospError) {
          // If hospital creation fails, we should ideally remove the user to allow retry
          await User.findByIdAndDelete(user._id);
          throw hospError;
        }
      }

    if (user) {
      res.status(201).json({
        _id: user._id,
        name: user.name,
        email: user.email,
        role: user.role,
        token: generateToken(user._id),
      });
    }
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
});

// @desc    Authenticate user & get token
// @route   POST /api/auth/login
router.post('/login', async (req, res) => {
  const { email, password } = req.body;
  try {
    const user = await User.findOne({ email });
    if (user && (await user.matchPassword(password))) {
      res.json({
        _id: user._id,
        name: user.name,
        email: user.email,
        role: user.role,
        token: generateToken(user._id),
      });
    } else {
      res.status(401).json({ message: 'Invalid email or password' });
    }
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
});

// @desc    Forgot Password - Generate OTP and Send Email
// @route   POST /api/auth/forgot-password
router.post('/forgot-password', async (req, res) => {
  const { email } = req.body;
  try {
    const user = await User.findOne({ email });
    if (!user) {
      return res.status(404).json({ message: 'User not found' });
    }

    // Generate 4-digit OTP
    const otp = Math.floor(1000 + Math.random() * 9000).toString();
    
    // Hash OTP before saving (optional, but good practice. For now we will save as plain string since it expires in 10mins)
    user.resetOtp = otp;
    user.resetOtpExpire = Date.now() + 10 * 60 * 1000; // 10 minutes
    await user.save();

    console.log(`[DEV ONLY] OTP for ${email} is: ${otp}`);

    // Set up Nodemailer transport
    // User can add credentials to .env later. Mocking sending for now if credentials are not provided.
    if (process.env.EMAIL_USER && process.env.EMAIL_PASS) {
      const transporter = nodemailer.createTransport({
        service: process.env.EMAIL_SERVICE || 'gmail',
        auth: {
          user: process.env.EMAIL_USER,
          pass: process.env.EMAIL_PASS,
        },
      });

      const mailOptions = {
        from: process.env.EMAIL_USER,
        to: user.email,
        subject: 'CareQueue - Password Reset OTP',
        text: `Your OTP for logging in is: ${otp}\n\nIt is valid for 10 minutes.`,
      };

      await transporter.sendMail(mailOptions);
      console.log('OTP Email sent successfully');
    } else {
      console.log('Skipping email send: No EMAIL_USER or EMAIL_PASS in .env. Use console OTP above.');
    }

    res.json({ message: 'OTP sent to email successfully' });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
});

// @desc    Verify OTP and Login
// @route   POST /api/auth/verify-otp-login
router.post('/verify-otp-login', async (req, res) => {
  const { email, otp } = req.body;
  try {
    const user = await User.findOne({ email });
    
    if (!user) {
      return res.status(404).json({ message: 'User not found' });
    }

    if (!user.resetOtp || user.resetOtp !== otp) {
      return res.status(400).json({ message: 'Invalid OTP' });
    }

    if (user.resetOtpExpire < Date.now()) {
      return res.status(400).json({ message: 'OTP has expired' });
    }

    // OTP is valid. Clear OTP fields.
    user.resetOtp = undefined;
    user.resetOtpExpire = undefined;
    await user.save();

    // Log user in
    res.json({
      _id: user._id,
      name: user.name,
      email: user.email,
      role: user.role,
      token: generateToken(user._id),
    });

  } catch (error) {
    res.status(500).json({ message: error.message });
  }
});

// @desc    Doctor Login (Hospital Code + Doctor ID)
// @route   POST /api/auth/doctor-login
router.post('/doctor-login', async (req, res) => {
  const { hospitalCode, docId } = req.body;
  try {
    // 1. Find Hospital by Code
    const hospital = await Hospital.findOne({ code: hospitalCode });
    if (!hospital) return res.status(404).json({ message: 'Hospital facility not found' });

    // 2. Find Doctor by docId within that Hospital
    const Doctor = require('../models/Doctor');
    const doctor = await Doctor.findOne({ hospital: hospital._id, docId: docId }).populate('department', 'name');
    
    if (!doctor) return res.status(401).json({ message: 'Doctor ID not recognized for this hospital' });

    // 3. Get associated User account
    const user = await User.findById(doctor.userId);
    if (!user) return res.status(500).json({ message: 'Clinical account linkage failed' });

    res.json({
      _id: user._id,
      name: doctor.name,
      email: user.email,
      role: 'doctor',
      doctor_info: {
        id: doctor._id,
        docId: doctor.docId,
        department: doctor.department?.name,
        departmentId: doctor.department?._id,
        hospitalName: hospital.name,
        hospitalId: hospital._id
      },
      token: generateToken(user._id)
    });
  } catch (error) {
    res.status(500).json({ message: error.message });
  }
});

const generateToken = (id) => {
  return jwt.sign({ id }, process.env.JWT_SECRET, { expiresIn: '30d' });
};

module.exports = router;
