const express = require('express');
const router = express.Router();
const { 
  getHospitals,
  getDiscoveryData,
  getMyHospital,
  createHospital, 
  updateHospital, 
  manageDepartment, 
  onboardDoctor, 
  handleLeave, 
  manageStaff, 
  getAnalytics,
  getDepartments,
  getDoctors,
  getStaff,
  getLeaves,
  applyLeave,
  getSchedules,
  manageSchedule,
  removeDoctor
} = require('../controllers/adminController');
const { protect, authorize } = require('../middleware/auth');

// Public Routes
router.get('/hospitals', getHospitals);
router.get('/hospitals/discovery', getDiscoveryData);
router.get('/departments', getDepartments);

router.use(protect);

// Hospital Profile
router.get('/hospitals/me', authorize('hospital_admin'), getMyHospital);
router.post('/hospitals', authorize('hospital_admin'), createHospital);
router.put('/hospitals/:id', authorize('hospital_admin'), updateHospital);

// Departments
router.post('/departments', authorize('hospital_admin'), (req, res) => {
  req.body.action = 'create';
  manageDepartment(req, res);
});
router.put('/departments/:id', authorize('hospital_admin'), manageDepartment);

// Doctors & Schedules
router.get('/doctors', authorize('hospital_admin', 'department_admin'), getDoctors);
router.post('/doctors/onboard', authorize('hospital_admin'), onboardDoctor);
router.delete('/doctors/:id', authorize('hospital_admin'), removeDoctor);
router.get('/schedules', authorize('hospital_admin', 'department_admin'), getSchedules);
router.post('/schedules', authorize('hospital_admin'), manageSchedule);

// Staff
router.get('/staff', authorize('hospital_admin'), getStaff);
router.post('/staff', authorize('hospital_admin'), manageStaff);

// Leaves
router.get('/leaves', authorize('hospital_admin', 'department_admin'), getLeaves);
router.post('/leaves/apply', applyLeave);
router.put('/leaves/:id/status', authorize('hospital_admin', 'department_admin'), handleLeave);

// Analytics
router.get('/analytics', authorize('hospital_admin', 'department_admin'), getAnalytics);

module.exports = router;
