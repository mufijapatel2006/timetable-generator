-- MariaDB dump 10.19  Distrib 10.4.32-MariaDB, for Win64 (AMD64)
--
-- Host: localhost    Database: timetable_database
-- ------------------------------------------------------
-- Server version	10.4.32-MariaDB

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `batch_faculty`
--

DROP TABLE IF EXISTS `batch_faculty`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `batch_faculty` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `class_id` int(11) DEFAULT NULL,
  `subject_id` int(11) DEFAULT NULL,
  `batch` varchar(10) DEFAULT NULL,
  `faculty_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `class_id` (`class_id`),
  KEY `subject_id` (`subject_id`),
  KEY `faculty_id` (`faculty_id`),
  CONSTRAINT `batch_faculty_ibfk_1` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`),
  CONSTRAINT `batch_faculty_ibfk_2` FOREIGN KEY (`subject_id`) REFERENCES `subjects` (`id`),
  CONSTRAINT `batch_faculty_ibfk_3` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=49 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `batch_faculty`
--

LOCK TABLES `batch_faculty` WRITE;
/*!40000 ALTER TABLE `batch_faculty` DISABLE KEYS */;
INSERT INTO `batch_faculty` VALUES (1,1,10,'A1',1),(2,1,10,'A2',1),(3,1,10,'A3',1),(4,1,10,'A4',1),(5,1,12,'A1',4),(6,1,12,'A2',4),(7,1,12,'A3',4),(8,1,12,'A4',4),(9,1,13,'A1',8),(10,1,13,'A2',8),(11,1,13,'A3',7),(12,1,13,'A4',7),(13,2,11,'A1',7),(14,2,11,'A2',7),(15,2,11,'A3',7),(16,2,11,'A4',7),(17,2,24,'A1',2),(18,2,24,'A2',2),(19,2,24,'A3',11),(20,2,24,'A4',11),(21,2,25,'A1',1),(22,2,25,'A2',1),(23,2,25,'A3',13),(24,2,25,'A4',13),(25,3,34,'A1',13),(26,3,34,'A2',13),(27,3,34,'A3',13),(28,3,34,'A4',13),(29,3,35,'A1',12),(30,3,35,'A2',12),(31,3,35,'A3',12),(32,3,35,'A4',12),(33,3,36,'A1',8),(34,3,36,'A2',2),(35,3,36,'A3',6),(36,3,36,'A4',6),(37,4,43,'A1',11),(38,4,43,'A2',11),(39,4,43,'A3',11),(40,4,43,'A4',11),(41,4,44,'A1',6),(42,4,44,'A2',6),(43,4,44,'A3',6),(44,4,44,'A4',6),(45,4,45,'A1',12),(46,4,45,'A2',4),(47,4,45,'A3',8),(48,4,45,'A4',2);
/*!40000 ALTER TABLE `batch_faculty` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `batch_subject`
--

DROP TABLE IF EXISTS `batch_subject`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `batch_subject` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `class_id` int(11) DEFAULT NULL,
  `batch` varchar(10) DEFAULT NULL,
  `subject_id` int(11) DEFAULT NULL,
  `faculty_id` int(11) DEFAULT NULL,
  `group_no` int(11) DEFAULT 1,
  PRIMARY KEY (`id`),
  KEY `class_id` (`class_id`),
  KEY `subject_id` (`subject_id`),
  KEY `faculty_id` (`faculty_id`),
  CONSTRAINT `batch_subject_ibfk_1` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`),
  CONSTRAINT `batch_subject_ibfk_2` FOREIGN KEY (`subject_id`) REFERENCES `subjects` (`id`),
  CONSTRAINT `batch_subject_ibfk_3` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `batch_subject`
--

LOCK TABLES `batch_subject` WRITE;
/*!40000 ALTER TABLE `batch_subject` DISABLE KEYS */;
/*!40000 ALTER TABLE `batch_subject` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `classes`
--

DROP TABLE IF EXISTS `classes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `classes` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `classes`
--

LOCK TABLES `classes` WRITE;
/*!40000 ALTER TABLE `classes` DISABLE KEYS */;
INSERT INTO `classes` VALUES (1,'SY-A'),(2,'SY-B'),(3,'TY-A'),(4,'TY-B');
/*!40000 ALTER TABLE `classes` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `faculty`
--

DROP TABLE IF EXISTS `faculty`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `faculty` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `faculty`
--

LOCK TABLES `faculty` WRITE;
/*!40000 ALTER TABLE `faculty` DISABLE KEYS */;
INSERT INTO `faculty` VALUES (1,'Mrs. P. R. Chougule'),(2,'Mr. A. B. Jagdale'),(3,'Ms. S. M. Zende'),(4,'Mrs. T. S. Mali'),(5,'Mr. R. D. Koshti'),(6,'Mrs U. V. Patil'),(7,'Mrs. P. R. Rajmane'),(8,'Mr. V. B. Dhere'),(9,'Mrs. A. V. Patil'),(10,'Mr. P. M. Karande'),(11,'Mr. K. B. Desai'),(12,'Ms. S. S. Parekh'),(13,'Mrs. D. D. Dhokate'),(14,'Ms. M. V. Pujari');
/*!40000 ALTER TABLE `faculty` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `rooms`
--

DROP TABLE IF EXISTS `rooms`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `rooms` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(50) DEFAULT NULL,
  `type` enum('Classroom','Lab') DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `rooms`
--

LOCK TABLES `rooms` WRITE;
/*!40000 ALTER TABLE `rooms` DISABLE KEYS */;
INSERT INTO `rooms` VALUES (1,'Classroom 1','Classroom'),(2,'Classroom 2','Classroom'),(3,'Classroom 3','Classroom'),(4,'Seminar','Classroom'),(5,'Lab 1','Lab'),(6,'Lab 2','Lab'),(7,'Lab 3','Lab'),(8,'Lab 4','Lab'),(9,'Lab 5','Lab'),(10,'Lab 6','Lab'),(11,'Lab 7','Lab'),(12,'Lab 8','Lab');
/*!40000 ALTER TABLE `rooms` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `subjects`
--

DROP TABLE IF EXISTS `subjects`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `subjects` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) DEFAULT NULL,
  `type` enum('Theory','Practical') DEFAULT NULL,
  `hours` int(11) DEFAULT NULL,
  `class_id` int(11) DEFAULT NULL,
  `faculty_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `class_id` (`class_id`),
  KEY `faculty_id` (`faculty_id`),
  CONSTRAINT `subjects_ibfk_1` FOREIGN KEY (`class_id`) REFERENCES `classes` (`id`),
  CONSTRAINT `subjects_ibfk_2` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=46 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `subjects`
--

LOCK TABLES `subjects` WRITE;
/*!40000 ALTER TABLE `subjects` DISABLE KEYS */;
INSERT INTO `subjects` VALUES (1,'CAO','Theory',3,1,2),(2,'P&S','Theory',3,1,3),(3,'OE','Theory',2,1,5),(4,'COI','Theory',2,1,9),(5,'LBBA','Theory',1,1,10),(6,'MARATHI','Theory',2,1,10),(7,'DAA','Theory',3,1,1),(8,'PYTHON','Theory',1,1,4),(9,'PYTHON','Theory',1,1,4),(10,'DAA','Practical',2,1,1),(11,'DAA','Practical',2,1,1),(12,'PYTHON','Practical',2,1,4),(13,'FSDP','Practical',16,1,7),(14,'ADC','Theory',2,1,6),(15,'CAO','Theory',3,2,8),(16,'P&S','Theory',3,2,3),(17,'OE','Theory',2,2,5),(18,'COI','Theory',2,2,9),(19,'LBBA','Theory',1,2,10),(20,'MARATHI','Theory',2,1,10),(21,'DAA','Theory',3,2,7),(22,'PYTHON','Theory',1,2,11),(23,'DAA','Practical',2,2,7),(24,'PYTHON','Practical',2,2,11),(25,'FSDP','Practical',16,2,13),(26,'ADC','Theory',2,2,12),(27,'CD','Theory',4,3,7),(28,'CN','Theory',4,3,4),(29,'IOT','Theory',3,3,8),(30,'ESD','Theory',3,3,6),(31,'ESD','Theory',3,3,6),(32,'ML','Theory',4,3,13),(33,'CPML','Theory',1,3,12),(34,'ML','Practical',2,3,13),(35,'CPML','Practical',2,3,12),(36,'MP','Practical',4,3,11),(37,'CD','Theory',4,4,14),(38,'CN','Theory',4,4,1),(39,'IOT','Theory',3,4,2),(40,'ESD','Theory',3,4,12),(41,'ML','Theory',4,4,11),(42,'CPML','Theory',1,4,6),(43,'ML','Practical',2,4,11),(44,'CPML','Practical',2,4,6),(45,'MP','Practical',4,4,11);
/*!40000 ALTER TABLE `subjects` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-23 13:19:29
