import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;

public class FileOperations {

    private static final int MAX_LINE = 256;

    public static int countLines(String filename) {
        try (BufferedReader reader = new BufferedReader(new FileReader(filename))) {
            int count = 0;
            String line;
            while ((line = reader.readLine()) != null) {
                count++;
            }
            return count;
        } catch (IOException e) {
            return -1;
        }
    }

    public static int copyFile(String src, String dst) {
        try (BufferedReader reader = new BufferedReader(new FileReader(src));
             BufferedWriter writer = new BufferedWriter(new FileWriter(dst))) {
            String line;
            while ((line = reader.readLine()) != null) {
                writer.write(line);
                writer.newLine();
            }
            return 0;
        } catch (IOException e) {
            return -1;
        }
    }

    public static int findInFile(String filename, String pattern) {
        try (BufferedReader reader = new BufferedReader(new FileReader(filename))) {
            int lineNum = 0;
            String line;
            while ((line = reader.readLine()) != null) {
                lineNum++;
                if (line.contains(pattern)) {
                    return lineNum;
                }
            }
            return 0;
        } catch (IOException e) {
            return -1;
        }
    }

    public static void main(String[] args) {
        int lines = countLines("test.txt");
        if (lines < 0) {
            System.out.println("Error opening file");
            System.exit(1);
        }
        System.out.println("Lines: " + lines);

        int result = copyFile("test.txt", "copy.txt");
        if (result == 0) {
            System.out.println("Copy successful");
        } else {
            System.out.println("Copy failed: " + result);
        }

        int found = findInFile("test.txt", "hello");
        if (found > 0) {
            System.out.println("Pattern found at line " + found);
        } else if (found == 0) {
            System.out.println("Pattern not found");
        } else {
            System.out.println("Error reading file");
        }
    }
}