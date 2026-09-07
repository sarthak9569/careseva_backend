const mongoose = require('mongoose');
require('dotenv').config();
const Department = require('./models/Department');

const departments = [
  { name: 'OPD', avg_consultation_time: 15 },
  { name: 'General Consultation', avg_consultation_time: 10 },
  { name: 'Emergency', avg_consultation_time: 5 },
  { name: 'Cardiology', avg_consultation_time: 20 },
  { name: 'Orthopedics', avg_consultation_time: 15 },
  { name: 'Pediatrics', avg_consultation_time: 12 },
  { name: 'General Medicine', avg_consultation_time: 10 },
  { name: 'Dermatology', avg_consultation_time: 15 },
  { name: 'ENT', avg_consultation_time: 10 },
  { name: 'Gynecology', avg_consultation_time: 15 },
];

const seedDB = async () => {
  try {
    await mongoose.connect(process.env.MONGODB_URI);
    console.log('Connected to MongoDB for seeding...');

    // Clear existing departments (optional, depends on use case)
    // await Department.deleteMany({}); 

    for (const dept of departments) {
      await Department.findOneAndUpdate(
        { name: dept.name },
        dept,
        { upsert: true, new: true }
      );
    }

    console.log('Seeding complete! Departments are ready.');
    process.exit(0);
  } catch (err) {
    console.error('Seeding error:', err);
    process.exit(1);
  }
};

seedDB();