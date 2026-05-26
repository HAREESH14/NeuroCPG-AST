import java.util.Scanner;

public class MatrixDet2x2 {
    public static void main(String[] args) {
        int[][] m = new int[2][2];
        int i, j;
        Scanner scanner = new Scanner(System.in);
        for (i = 0; i < 2; ++i) {
            for (j = 0; j < 2; ++j) {
                m[i][j] = scanner.nextInt();
            }
        }
        int det = m[0][0]*m[1][1] - m[0][1]*m[1][0];
        System.out.println("Determinant: " + det);
    }
}